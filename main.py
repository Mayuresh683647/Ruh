# main.py
import os
import re
import shutil
import zipfile
import asyncio
import aiohttp
from pathlib import Path
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import FSInputFile, InputFile
from aiogram.enums import ParseMode
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import CommandStart, Command

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)

bot = Bot(token=TOKEN)
dp = Dispatcher()

# Helper function to extract URLs
def extract_links(text):
    return re.findall(r"(https?://[\w./?=&-]+)", text or "")

# Start command
@dp.message(CommandStart())
async def start_command(msg: types.Message):
    kb = InlineKeyboardBuilder()
    kb.button(text="Send Links or Upload .txt File", callback_data="info")
    await msg.answer("Welcome! Send TeraBox/DiskWala/XDisk links or upload a .txt file.", reply_markup=kb.as_markup())

@dp.callback_query(F.data == "info")
async def show_info(callback: types.CallbackQuery):
    await callback.message.answer("Send single/multiple links or upload a .txt file to process.")
    await callback.answer()

# Handle normal text links
@dp.message(F.text)
async def handle_links(msg: types.Message):
    links = extract_links(msg.text)
    if not links:
        return await msg.answer("No valid link found.")
    for link in links:
        kb = InlineKeyboardBuilder()
        kb.button(text="PLAYER", url=link)  # Placeholder
        kb.button(text="DOWNLOAD", url=link)
        await msg.answer(f"Link: {link}", reply_markup=kb.as_markup())

# Handle .txt upload
@dp.message(F.document)
async def handle_text_file(msg: types.Message):
    if not msg.document.file_name.endswith(".txt"):
        return await msg.answer("Only .txt files allowed.")

    file_path = TEMP_DIR / msg.document.file_name
    await bot.download(msg.document, destination=file_path)

    kb = InlineKeyboardBuilder()
    kb.button(text="Create Folder", callback_data=f"create_folder:{file_path}")
    await msg.answer("File received. Click below to create folders.", reply_markup=kb.as_markup())

# Simulate download with fake file size
async def fake_download(link):
    await asyncio.sleep(0.2)  # Simulate delay
    size = int(len(link) * 10e4) % 300_000_000 + 20_000_000  # 20MB–300MB
    return link, size

# Folder splitting logic
@dp.callback_query(F.data.startswith("create_folder:"))
async def create_folders(callback: types.CallbackQuery):
    file_path = Path(callback.data.split(":", 1)[1])
    if not file_path.exists():
        return await callback.message.answer("File not found.")

    links = extract_links(file_path.read_text())
    folders = []
    folder_idx = 1
    current_size = 0
    current_files = []
    total_files = 0

    for link in links:
        fname, size = await fake_download(link)
        total_files += 1
        if current_size + size > 500_000_000:
            folders.append((folder_idx, list(current_files)))
            folder_idx += 1
            current_files = []
            current_size = 0
        current_files.append((fname, size))
        current_size += size

    if current_files:
        folders.append((folder_idx, current_files))

    for idx, files in folders:
        folder_path = TEMP_DIR / f"Folder_{idx}"
        folder_path.mkdir(exist_ok=True)
        for f, s in files:
            (folder_path / f"file_{abs(hash(f)) % 10000}.bin").write_bytes(os.urandom(1024 * 1024))  # 1MB dummy
        zip_path = shutil.make_archive(str(folder_path), 'zip', folder_path)
        await callback.message.answer_document(InputFile(zip_path), caption=f"Download Folder {idx}")

    await callback.message.answer(f"✅ Total Files Processed: {total_files}\n📁 Total Folders Created: {len(folders)}")
    await callback.answer()

# Clear system command
@dp.message(Command("clear"))
async def clear_cache(msg: types.Message):
    if msg.from_user.id != ADMIN_ID:
        return await msg.answer("Access denied.")
    shutil.rmtree(TEMP_DIR, ignore_errors=True)
    TEMP_DIR.mkdir(exist_ok=True)
    await msg.answer("System cleaned. Bot is fresh now.")

# Main runner
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

