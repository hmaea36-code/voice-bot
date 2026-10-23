import json
import asyncio
import discord
from discord.ext import tasks

# ============ قراءة التكوين ============
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

GUILD_ID = config['guild_id']
CHECK_INTERVAL = config.get('check_interval_seconds', 300)
BOTS = config.get('bots', [])


class VoiceKeeper:
    """بوت واحد يحافظ على اتصاله بقناة صوتية مخصصة"""

    def __init__(self, name: str, token: str, voice_channel_id):
        self.name = name
        self.token = token
        self.voice_channel_id = voice_channel_id

        intents = discord.Intents.default()
        intents.voice_states = True
        self.client = discord.Client(intents=intents)
        self.voice_client = None
        self._register_events()

    # ---------- الأحداث ----------
    def _register_events(self):
        @self.client.event
        async def on_ready():
            print(f'[{self.name}] ✅ تم تسجيل الدخول كـ {self.client.user}')
            if self.voice_channel_id is None:
                print(f'[{self.name}] ⚠ لا توجد قناة مخصصة (voice_channel_id = null)، لن ينضم لأي روم.')
                return
            if not self.keep_alive.is_running():
                self.keep_alive.start()

        @self.client.event
        async def on_disconnect():
            print(f'[{self.name}] ⚠ انقطع اتصال WebSocket، سيعيد Discord المحاولة تلقائياً.')

        @self.client.event
        async def on_resumed():
            print(f'[{self.name}] 🔄 تم استئناف الجلسة.')

    # ---------- الحلقة الدورية ----------
    @tasks.loop(seconds=CHECK_INTERVAL)
    async def keep_alive(self):
        if self.voice_channel_id is None:
            return

        # جلب القناة من الـ API (وليس من الكاش)
        try:
            channel = await self.client.fetch_channel(self.voice_channel_id)
        except discord.NotFound:
            print(f'[{self.name}] ❌ القناة {self.voice_channel_id} غير موجودة (معرف خاطئ أو محذوفة).')
            return
        except discord.Forbidden:
            print(f'[{self.name}] ❌ البوت لا يملك صلاحية رؤية القناة {self.voice_channel_id}.')
            return
        except Exception as e:
            print(f'[{self.name}] ❌ خطأ أثناء جلب القناة: {e}')
            return

        if not isinstance(channel, discord.VoiceChannel):
            print(f'[{self.name}] ❌ المعرف {self.voice_channel_id} ليس قناة صوتية.')
            return

        # الحالة 1: لا يوجد اتصال → اتصل
        if self.voice_client is None or not self.voice_client.is_connected():
            print(f'[{self.name}] 🔌 محاولة الاتصال بـ "{channel.name}"...')
            try:
                if self.voice_client is not None:
                    await self.voice_client.disconnect(force=True)
                self.voice_client = await channel.connect(self_deaf=True, timeout=30.0)
                print(f'[{self.name}] ✅ تم الاتصال بـ "{channel.name}"')
            except discord.Forbidden:
                print(f'[{self.name}] ❌ لا يملك صلاحية Connect في "{channel.name}"')
            except asyncio.TimeoutError:
                print(f'[{self.name}] ❌ انتهت مهلة الاتصال الصوتي (غالباً مشكلة شبكة/UDP).')
            except Exception as e:
                print(f'[{self.name}] ❌ فشل الاتصال: {e}')
            return

        # الحالة 2: متصل لكن في قناة خاطئة → أعده
        if self.voice_client.channel.id != self.voice_channel_id:
            print(f'[{self.name}] ↩ البوت في قناة خاطئة، جاري إرجاعه...')
            try:
                await self.voice_client.move_to(channel)
                print(f'[{self.name}] ✅ تم إرجاعه إلى "{channel.name}"')
            except Exception as e:
                print(f'[{self.name}] ❌ فشل النقل: {e}')
            return

        # الحالة 3: كل شيء سليم
        print(f'[{self.name}] ✔ الاتصال طبيعي في "{channel.name}"')

    @keep_alive.before_loop
    async def before_keep_alive(self):
        await self.client.wait_until_ready()

    @keep_alive.error
    async def keep_alive_error(self, error):
        print(f'[{self.name}] ⚠ خطأ داخل الحلقة الدورية: {error}')

    # ---------- التشغيل ----------
    async def start(self):
        try:
            await self.client.start(self.token)
        except discord.LoginFailure:
            print(f'[{self.name}] ❌ التوكن غير صالح (LoginFailure).')
        except Exception as e:
            print(f'[{self.name}] ❌ توقف البوت بسبب خطأ: {e}')


async def main():
    if not BOTS:
        print('❌ لا توجد بوتات في config.json (مصفوفة bots فارغة).')
        return

    keepers = []
    for b in BOTS:
        name = b.get('name', 'bot?')
        token = b.get('token')
        vid = b.get('voice_channel_id')

        if not token or token.startswith('التوكن'):
            print(f'[{name}] ⚠ تم تخطيه: التوكن غير مضبوط.')
            continue
        if vid is not None and not isinstance(vid, int):
            print(f'[{name}] ⚠ voice_channel_id يجب أن يكون رقماً أو null. القيمة الحالية: {vid!r}')
            continue

        keepers.append(VoiceKeeper(name, token, vid))

    if not keepers:
        print('❌ لا يوجد بوت صالح للتشغيل.')
        return

    print(f'🚀 جاري تشغيل {len(keepers)} بوت...')
    await asyncio.gather(*(k.start() for k in keepers), return_exceptions=True)


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('\n👋 تم الإيقاف يدوياً.')