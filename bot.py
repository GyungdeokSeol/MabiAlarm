import discord
from discord.ext import tasks, commands
import requests
from bs4 import BeautifulSoup
import json
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

CONFIG_FILE = 'bot_config.json'

def load_channel_id():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return data.get('channel_id')
    return None

def save_channel_id(channel_id):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'channel_id': channel_id}, f)

# --- [새로 추가된 부분] 공지 크롤링 전용 함수 ---
def get_latest_notice():
    url = "https://mabinogi.nexon.com/page/news/notice_list.asp"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
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
            
            # 가장 최신 글 1개의 제목과 링크만 찾아서 바로 넘겨줍니다.
            return title, link
            
    except Exception as e:
        print(f"크롤링 오류 발생: {e}")
        
    return None, None
# ---------------------------------------------

intents = discord.Intents.default()
intents.message_content = True 

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=intents)
    
    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()
target_channel_id = load_channel_id()
last_notice_link = ""

@bot.tree.command(name="채널", description="현재 이 채널을 공지사항 알림 채널로 설정합니다.")
async def set_channel(interaction: discord.Interaction):
    global target_channel_id, last_notice_link
    
    current_channel = interaction.channel
    target_channel_id = current_channel.id 
    save_channel_id(current_channel.id) 
    
    # 1. 안내 메시지 먼저 전송
    await interaction.response.send_message(f"✅ 알림 채널이 {current_channel.mention}로 설정되었습니다!\n작동 확인을 위해 최신 공지를 불러옵니다 🚀")
    
    # 2. [추가된 부분] 채널 설정 즉시 최신 공지를 가져와서 '연결 테스트'로 띄워줍니다.
    title, link = get_latest_notice()
    if title and link:
        last_notice_link = link  # 이 글을 마지막 글로 기억합니다.
        await current_channel.send(f"📢 **[연결 테스트] 현재 최신 공지사항**\n**{title}**\n{link}")
    else:
        await current_channel.send("⚠️ 공지사항을 불러오는 데 실패했습니다.")

@tasks.loop(minutes=15)
async def check_notices():
    global last_notice_link, target_channel_id
    
    if target_channel_id is None:
        return

    # 크롤링 함수를 불러와서 최신 글을 확인합니다.
    title, link = get_latest_notice()
    
    if title and link:
        # (봇이 재시작되었을 때 등) 처음 상태라면 조용히 기억만 하고 넘어갑니다.
        if last_notice_link == "":
            last_notice_link = link
            print(f"초기화 완료. 최신 공지: {title}")
            return

        # 기억하고 있던 링크와 다르다면 (새 글이 올라왔다면)
        if link != last_notice_link:
            channel = bot.get_channel(target_channel_id)
            if channel:
                await channel.send(f"🚨 **마비노기 새 공지사항** 🚨\n**{title}**\n{link}")
            last_notice_link = link
            print(f"새 공지사항 전송 완료: {title}")

@bot.event
async def on_ready():
    print(f'✅ {bot.user} 로그인 완료. 저장된 채널 ID: {target_channel_id}')
    if not check_notices.is_running():
        check_notices.start()

bot.run(TOKEN)