import asyncio
import os
import sys
from playwright.async_api import async_playwright

async def run():
    video_dir = "/config/.gemini/antigravity/brain/f50de7d1-e787-4a94-b31c-aab82ff85218"
    os.makedirs(video_dir, exist_ok=True)
    
    print("Launching browser with video recording enabled...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            record_video_dir=video_dir,
            record_video_size={"width": 1280, "height": 800},
            viewport={"width": 1280, "height": 800}
        )
        page = await context.new_page()

        print("Navigating to playground at http://127.0.0.1:8080/dev-ui/?app=app ...")
        await page.goto("http://127.0.0.1:8080/dev-ui/?app=app")
        await page.wait_for_timeout(3000)

        # Locate chat input textbox
        print("Finding chat input...")
        input_elem = await page.wait_for_selector("textarea, input[type='text'], [contenteditable='true']", timeout=10000)
        
        # 1. Ask it to scan microsoft.com
        print("Prompt 1: Asking agent to scan microsoft.com...")
        await input_elem.fill("Scan microsoft.com")
        await page.wait_for_timeout(500)
        await page.keyboard.press("Enter")

        # Wait 30000ms as requested
        print("Waiting 30000ms for scan response to finish...")
        await page.wait_for_timeout(30000)

        # 2. Ask it to show all scans in a table
        print("Prompt 2: Asking agent to show all scans in a table...")
        input_elem = await page.wait_for_selector("textarea, input[type='text'], [contenteditable='true']", timeout=10000)
        await input_elem.fill("Show all scans in a table")
        await page.wait_for_timeout(500)
        await page.keyboard.press("Enter")

        # Wait 30000ms as requested
        print("Waiting 30000ms for second response to finish...")
        await page.wait_for_timeout(30000)

        print("Capturing final screenshot...")
        await page.screenshot(path=os.path.join(video_dir, "demo_playground.png"))

        # Close page and context to finalize video
        video_path = await page.video.path()
        print(f"Temporary video file: {video_path}")
        await page.close()
        await context.close()
        await browser.close()

        final_video = os.path.join(video_dir, "playground_demo.webm")
        if os.path.exists(video_path):
            if os.path.exists(final_video):
                os.remove(final_video)
            os.rename(video_path, final_video)
            print(f"Demo recording saved successfully to: {final_video}")

asyncio.run(run())
