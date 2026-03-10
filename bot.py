import discord
from discord.ext import tasks, commands
import requests
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

CONFIG_FILE = 'bot_config.json'

# --- [수정됨] 여러 서버의 채널을 관리하는 함수 ---
def load_channels():
    # 파일이 존재하면 딕셔너리(장부) 형태로 불러옵니다.
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                # 만약 예전 방식(단일 채널)의 파일이라면 빈 장부로 초기화합니다.
                if 'channel_id' in data:
                    return {}
                return data
        except json.JSONDecodeError:
            return {}
    return {} # 파일이 없으면 텅 빈 장부를 반환합니다.

def save_channel(guild_id, channel_id):
    channels = load_channels()
    # 장부에 "서버ID": "채널ID" 형태로 기록합니다.
    channels[str(guild_id)] = channel_id
    with open(CONFIG_FILE, 'w') as f:
        json.dump(channels, f)
# ---------------------------------------------

def fetch_all_notices():
    url = "https://mabinogi.nexon.com/page/news/notice_list.asp"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    notices = []
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        notice_elements = soup.select("a[href*='notice_view.asp']")
        
        for element in notice_elements:
            title = element.text.strip()
            if not title:
                continue
            
            raw_link = element['href']
            if raw_link.startswith("http"):
                link = raw_link
            else:
                link = f"https://mabinogi.nexon.com{raw_link if raw_link.startswith('/') else '/page/news/' + raw_link}"
            
            notices.append((title, link))
            
        return notices
            
    except Exception as e:
        print(f"크롤링 오류 발생: {e}")
        return []

intents = discord.Intents.default()
intents.message_content = True 

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
    
    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()
last_notice_link = ""

@bot.tree.command(name="채널", description="현재 이 채널을 공지사항 알림 채널로 설정합니다.")
async def set_channel(interaction: discord.Interaction):
    global last_notice_link
    
    guild_id = interaction.guild_id # 명령어를 친 서버의 ID
    current_channel = interaction.channel
    
    # 해당 서버의 ID와 채널 ID를 매칭하여 저장합니다.
    save_channel(guild_id, current_channel.id) 
    
    await interaction.response.send_message(f"✅ 알림 채널이 {current_channel.mention}로 설정되었습니다!\n작동 확인을 위해 최신 공지를 불러옵니다 🚀")
    
    notices = fetch_all_notices()
    if notices:
        title, link = notices[0]
        # 첫 등록 시 전체 봇의 '마지막 공지' 기준을 잡아줍니다.
        if last_notice_link == "":
            last_notice_link = link  
        await current_channel.send(f"📢 **[연결 테스트] 현재 최신 공지사항**\n**{title}**\n{link}")
    else:
        await current_channel.send("⚠️ 공지사항을 불러오는 데 실패했습니다.")

@tasks.loop(minutes=15)
async def check_notices():
    global last_notice_link
    
    # 등록된 모든 서버-채널 목록을 불러옵니다.
    target_channels = load_channels()
    
    # 등록된 채널이 단 한 곳도 없으면 크롤링하지 않고 넘어갑니다.
    if not target_channels:
        return

    notices = fetch_all_notices()
    if not notices:
        return

    if last_notice_link == "":
        last_notice_link = notices[0][1]
        print(f"초기화 완료. 최신 공지: {notices[0][0]}")
        return

    new_notices = []
    for title, link in notices:
        if link == last_notice_link:
            break
        new_notices.append((title, link))
    
    if new_notices:
        new_notices.reverse() 
        
        for title, link in new_notices:
            message_content = f"🚨 **마비노기 새 공지사항** 🚨\n**{title}**\n{link}"
            
            # 🌟 핵심: 등록된 "모든" 채널을 돌면서 메시지를 발송합니다.
            for guild_id, channel_id in target_channels.items():
                channel = bot.get_channel(int(channel_id))
                if channel:
                    try:
                        await channel.send(message_content)
                    except Exception as e:
                        print(f"서버({guild_id}) 채널({channel_id}) 전송 실패: {e}")
        
        last_notice_link = new_notices[-1][1]
        print(f"등록된 모든 서버에 {len(new_notices)}개의 새 공지사항 전송 완료")

@bot.event
async def on_ready():
    print(f'✅ {bot.user} 로그인 완료. 다중 서버 지원 모드 가동!')
    if not check_notices.is_running():
        check_notices.start()

bot.run(TOKEN)