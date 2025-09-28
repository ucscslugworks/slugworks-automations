# pip install playwright

# playwright install
import json, asyncio
from pathlib import Path
from playwright.async_api import async_playwright

EMAIL = "slugworks@ucsc.edu"
PASSWORD = ""
ORIGIN = "https://bambulab.com"   # or the exact host you see
OUT = Path(__file__).resolve().parents[2] / "common" / "bambu.json"

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # let CF see a real browser
        ctx = await browser.new_context()
        page = await ctx.new_page()
        await page.goto(ORIGIN + "/", wait_until="load")
        await page.goto(ORIGIN + "/sign-in", wait_until="load")
        await page.fill('input[name="account"]', EMAIL)
        await page.fill('input[name="password"]', PASSWORD)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle")
        # Try to fetch an API endpoint so Authorization is used
        await page.goto(ORIGIN + "/api/v1/user-service/my/tasks")
        # Pull tokens: Authorization header is not directly exposed, so use cookies for refresh
        cookies = {c["name"]: c["value"] for c in await ctx.cookies() if c["domain"].endswith("bambulab.com")}
        rt = cookies.get("refreshToken")
        if not rt or "." not in rt:
            raise RuntimeError("Didn't find a JWT refreshToken; make sure you're on the API origin and fully logged in.")
        # Exchange refresh for fresh JWTs
        resp = await page.request.post(ORIGIN + "/api/v1/user-service/user/refreshtoken",
                                       data={"refreshToken": rt})
        j = await resp.json()
        access = j.get("accessToken"); refresh = j.get("refreshToken")
        if not access or "." not in access or not refresh or "." not in refresh:
            raise RuntimeError("Refresh did not return JWTs.")
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps({"token": access, "refreshToken": refresh}, indent=2))
        print("Wrote", OUT)
        await browser.close()

asyncio.run(main())
