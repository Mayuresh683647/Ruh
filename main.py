
import os
import re
import shutil
import zipfile
import aiohttp
import asyncio
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.enums import ParseMode
from aiogram.types import FSInputFile, InputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart, Command

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID") or 0)
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher()

# Extract real download URL and metadata (simplified, scraping-based fallback)
async def extract_file_info(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers={"User-Agent": "Mozilla/5.0"}) as resp:
            html = await resp.text()
            match = re.search(r'"download_url":"(https:[^"]+)"', html)
            name = re.search(r'"filename":"([^"]+)"', html)
            size = re.search(r'"file_size":(\d+)', html)

            if not match:
                return None

            return {
                "filename": name.group(1) if name else "file_from_link",
                "download_url": match.group(1).replace("\u002F", "/"),
                "size": int(size.group(1)) if size else 0,
                "type": "video/mp4" if ".mp4" in url else "file"
            }

# Download file
async def download_file(file_info, save_dir):
    filename = file_info["filename"]
    url = file_info["download_url"]
    path = save_dir / filename

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            with open(path, "wb") as f:
                while True:
                    chunk = await resp.content.read(1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
    return path

def extract_links(text):
    return re.findall(r"(https?://[\w./?=&%-]+)", text or "")

# Telegram commands and logic
@dp.message(CommandStart())
async def start_cmd(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="Send Links or Upload .txt File", callback_data="info")
    await msg.answer("Welcome! Send a TeraBox-style link or a .txt file to begin.", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "info")
async def info_cb(cb: types.CallbackQuery):
    await cb.message.answer("Paste links or upload a .txt file. Bot will download and organize.")
    await cb.answer()

@dp.message(F.text)
async def handle_links(msg: types.Message):
    links = extract_links(msg.text)
    if not links:
        return await msg.answer("No valid links found.")

    for link in links:
        info = await extract_file_info(link)
        if not info:
            await msg.answer(f"Failed to extract info from: {link}")
            continue

        temp_path = TEMP_DIR / info["filename"]
        await download_file(info, TEMP_DIR)
        file = FSInputFile(temp_path)

        kb = InlineKeyboardBuilder()
        kb.button(text="PLAYER", callback_data="noop")
        kb.button(text="PLAYER-2", callback_data="noop")
        kb.button(text="PLAYER-3", callback_data="noop")
        kb.button(text="DOWNLOAD", url=info["download_url"])
        await msg.answer_document(file, caption=f"{info['filename']} ({round(info['size']/1024/1024, 2)}MB)", reply_markup=kb.as_markup())

@dp.message(F.document)
async def handle_txt_file(msg: types.Message):
    if not msg.document.file_name.endswith(".txt"):
        return await msg.answer("Only .txt files are supported.")
    path = TEMP_DIR / msg.document.file_name
    await bot.download(msg.document, destination=path)

    kb = InlineKeyboardBuilder()
    kb.button(text="Create Folder", callback_data=f"create_folder:{path}")
    await msg.answer("Text file received. Click to begin folder creation.", reply_markup=kb.as_markup())

@dp.callback_query(F.data.startswith("create_folder:"))
async def create_folders(cb: types.CallbackQuery):
    path = Path(cb.data.split(":", 1)[1])
    if not path.exists():
        return await cb.message.answer("File not found.")
    links = extract_links(path.read_text())

    folders, folder_idx, current_files, current_size = [], 1, [], 0

    for link in links:
        info = await extract_file_info(link)
        if not info:
            continue
        fpath = await download_file(info, TEMP_DIR)
        size = fpath.stat().st_size

        if current_size + size > 500_000_000:
            folders.append((folder_idx, list(current_files)))
            folder_idx += 1
            current_files, current_size = [], 0

        current_files.append(fpath)
        current_size += size

    if current_files:
        folders.append((folder_idx, current_files))

    for idx, files in folders:
        folder_path = TEMP_DIR / f"Folder_{idx}"
        folder_path.mkdir(exist_ok=True)
        for f in files:
            shutil.copy(f, folder_path)
        zip_path = shutil.make_archive(str(folder_path), 'zip', folder_path)
        file = FSInputFile(f"{zip_path}")
        kb = InlineKeyboardBuilder()
        kb.button(text=f"Download Folder {idx}", callback_data="noop")
        kb.button(text="Save to Group/Channel", callback_data="noop")
        await cb.message.answer_document(file, caption=f"📁 Folder {idx} - {len(files)} files", reply_markup=kb.as_markup())

    await cb.message.answer(f"✅ Total Files Processed: {len(links)}\n📁 Total Folders Created: {len(folders)}")
    await cb.answer()

@dp.message(Command("clear"))
async def clear_cache(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("Access denied.")
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(exist_ok=True)
    await msg.answer("System cleaned. Bot is fresh again.")

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
