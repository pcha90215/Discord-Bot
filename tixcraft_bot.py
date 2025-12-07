import discord
from discord.ext import commands, tasks
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import datetime
import time  # 時間模組
import random
import asyncio
import traceback

# ================= ⚠️ 設定區 ⚠️ =================
TOKEN = '輸入token' #Discord developers -> Bot -> Reset Token
# ===============================================

intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

# 全域設定
config = {
    "url": None,
    "channel_id": None,
    "interval": 120, # 預設值
    "is_running": False
}

driver = None

def get_driver():
    global driver
    if driver is not None:
        return driver

    print("🚀 正在啟動瀏覽器...")
    chrome_options = Options()
    chrome_options.add_argument('--headless') 
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--log-level=3')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver

def check_tixcraft_fast():
    """
    爬蟲核心邏輯
    """
    global driver, config
    found_tickets = []
    
    target_url = config["url"]
    if not target_url:
        return []

    try:
        if driver is None:
            get_driver()

        driver.get(target_url)

        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
        except:
            pass 

        # 為了 5 秒極速模式，稍微縮短隨機延遲，但還是保留一點點避免太像機器人
        time.sleep(random.uniform(1, 2))
        
        page_source = driver.page_source
        
        if "Challenge" in driver.title or "Verify you are human" in page_source:
            print("⚠️ [警告] 遇到 Cloudflare 驗證，本次跳過")
            try: driver.quit()
            except: pass
            driver = None 
            return []

        soup = BeautifulSoup(page_source, 'html.parser')
        elements = soup.find_all(string=lambda text: text and "剩餘" in text)
        
        if elements:
            print(f"✅ [發現] 網頁中找到 {len(elements)} 個「剩餘」關鍵字！")
            for text in elements:
                full_text = ""
                row_container = text.find_parent('li')
                if row_container:
                    full_text = row_container.get_text(separator=' ', strip=True)
                
                if not full_text and text.parent and text.parent.parent:
                    full_text = text.parent.parent.get_text(separator=' ', strip=True)

                if not full_text:
                    full_text = f"未知區域 - {text.strip()}"

                if len(full_text) < 150:
                    found_tickets.append(full_text)
            
            return list(set(found_tickets))

        print(f"💤 [{datetime.datetime.now().strftime('%H:%M:%S')}] 掃描正常，但目前無票")
        return []

    except Exception as e:
        print(f"❌ [錯誤] 爬蟲發生異常: {e}")
        traceback.print_exc()
        if driver:
            try: driver.quit()
            except: pass
        driver = None
        return []

@tasks.loop(seconds=120) 
async def monitor_task():
    if not config["is_running"] or not config["url"]:
        return

    channel = bot.get_channel(config["channel_id"])
    if not channel:
        print("❌ [錯誤] 找不到頻道 ID，無法發送通知")
        return

    # 使用 asyncio.to_thread 避免卡住機器人指令
    tickets = await asyncio.to_thread(check_tixcraft_fast)
    
    if len(tickets) > 0:
        print("📤 [通知] 發現票券，正在發送 Discord 訊息...")
        ticket_info = "\n".join(tickets)
        try:
            await channel.send(
                f"🚨 **發現票券！** 🚨\n"
                f"網址: {config['url']}\n"
                f"----------------------------\n"
                f"{ticket_info}\n"
                f"----------------------------\n"
                f"@everyone"
            )
        except Exception as e:
            print(f"❌ [錯誤] 發送訊息失敗 (權限不足?): {e}")

# === 指令區 (已加入中文說明) ===

@bot.event
async def on_ready():
    print(f'機器人已登入: {bot.user}')
    print('請在 Discord 輸入 !help 查看指令')
    monitor_task.start()

@bot.command(help="測試機器人是否能在當前頻道說話")
async def test(ctx):
    try:
        await ctx.send("✅ **測試成功！** 我可以在這個頻道說話。")
    except Exception as e:
        print(f"❌ [錯誤] !test 指令失敗: {e}")

@bot.command(help="設定要監控的拓元網址\n用法: !url https://tixcraft.com/...")
async def url(ctx, link: str):
    config["url"] = link
    config["channel_id"] = ctx.channel.id 
    await ctx.send(f"✅ 已設定網址，通知頻道: {ctx.channel.name}")

@bot.command(name='time', help="設定檢查頻率 (秒)\n用法: !time 10 (最低 5 秒)")
async def set_interval(ctx, seconds: int):
    # 修改限制：從 60 改為 5
    if seconds < 5:
        await ctx.send("❌ 太快了！最低限制為 **5** 秒。")
        return
    
    config["interval"] = seconds
    monitor_task.change_interval(seconds=seconds)
    await ctx.send(f"⏱️ 頻率已更新: 每 **{seconds}** 秒檢查一次")

@bot.command(help="開始執行監控任務")
async def start(ctx):
    if not config["url"]:
        await ctx.send("❌ 請先輸入 `!url <網址>`")
        return
    
    config["is_running"] = True
    config["channel_id"] = ctx.channel.id
    
    await ctx.send("🚀 **開始監控！** (請留意 VS Code 終端機日誌)")

@bot.command(help="暫停監控任務")
async def stop(ctx):
    config["is_running"] = False
    await ctx.send("⏸️ 已暫停")

@bot.command(help="查看目前的設定狀態與網址")
async def status(ctx):
    status_msg = "🟢 運行中" if config["is_running"] else "🔴 已暫停"
    url_msg = config["url"] if config["url"] else "尚未設定"
    
    await ctx.send(
        f"📊 **目前狀態**\n"
        f"狀態: {status_msg}\n"
        f"頻率: 每 {config['interval']} 秒\n"
        f"網址: {url_msg}"
    )

import atexit
def exit_handler():
    if driver: driver.quit()
atexit.register(exit_handler)

if __name__ == "__main__":
    bot.run(TOKEN)