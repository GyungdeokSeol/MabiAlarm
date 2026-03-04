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

def load_channel_id():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            data = json.load(f)
            return data.get('channel_id')
    return None

def save_channel_id(channel_id):
    with open(CONFIG_FILE, 'w') as f:
        json.dump({'channel_id': channel_id}, f)

# --- [수정됨] 1페이지의 모든 공지사항을 가져오는 함수 ---
def fetch_all_notices():
    url = "https://mabinogi.nexon.com/page/news/notice_list.asp"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    notices = [] # 공지사항들을 담을 빈 리스트
    
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
            
            # (제목, 링크) 세트로 묶어서 리스트에 추가합니다.
            notices.append((title, link))
            
        return notices
            
    except Exception as e:
        print(f"크롤링 오류 발생: {e}")
        return []
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
    
    await interaction.response.send_message(f"✅ 알림 채널이 {current_channel.mention}로 설정되었습니다!\n작동 확인을 위해 최신 공지를 불러옵니다 🚀")
    
    # 전체 공지사항 중 첫 번째(가장 최신) 글만 가져와서 테스트용으로 띄웁니다.
    notices = fetch_all_notices()
    if notices:
        title, link = notices[0]
        last_notice_link = link  
        await current_channel.send(f"📢 **[연결 테스트] 현재 최신 공지사항**\n**{title}**\n{link}")
    else:
        await current_channel.send("⚠️ 공지사항을 불러오는 데 실패했습니다.")

@tasks.loop(minutes=15)
async def check_notices():
    global last_notice_link, target_channel_id
    
    if target_channel_id is None:
        return

    notices = fetch_all_notices()
    if not notices:
        return

    # 처음 시작 시: 제일 최신 글 하나만 기억하고 종료
    if last_notice_link == "":
        last_notice_link = notices[0][1]
        print(f"초기화 완료. 최신 공지: {notices[0][0]}")
        return

    new_notices = []
    # 목록을 위에서부터 차례대로 확인합니다.
    for title, link in notices:
        if link == last_notice_link:
            # 기억하던 링크를 만나면, 그 아래는 이미 올린 옛날 글이므로 반복을 멈춥니다.
            break
        # 기억하던 링크가 아니라면 새 글이므로 임시 보관함에 넣습니다.
        new_notices.append((title, link))
    
    # 새 글이 1개라도 있다면 디스코드에 전송합니다.
    if new_notices:
        channel = bot.get_channel(target_channel_id)
        if channel:
            # 먼저 올라온 공지가 먼저 전송되도록 리스트 순서를 뒤집습니다. (오래된 순 -> 최신 순)
            new_notices.reverse() 
            
            for title, link in new_notices:
                await channel.send(f"🚨 **마비노기 새 공지사항** 🚨\n**{title}**\n{link}")
        
        # 마지막으로 디스코드에 보낸 가장 최신 글(리스트의 맨 마지막 요소)을 기억합니다.
        last_notice_link = new_notices[-1][1]
        print(f"{len(new_notices)}개의 새 공지사항 전송 완료")

@bot.event
async def on_ready():
    print(f'✅ {bot.user} 로그인 완료. 저장된 채널 ID: {target_channel_id}')
    if not check_notices.is_running():
        check_notices.start()

bot.run(TOKEN)