import asyncio
from arq.connections import RedisSettings
from playwright.async_api import async_playwright, Browser
import numpy as np
import csv
import os
import pandas as pd
from time import sleep
from pathlib import Path
import re
from datetime import datetime
import openpyxl

BASE_DIR = Path(__file__).resolve().parent
# ==========================================
# 1. YOUR EXISTING SCRAPERS (Safely Adapted)
# ==========================================
def timestamp():
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return ts

def append_product_to_csv(item, url, price, pta_qty, jhb_qty, cpt_qty,sku,status, filename="GOG_detailed.csv"):
    """
    Appends a product record to a CSV file with timestamp.
    """
    # Add a timestamp column
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_timestamp = datetime.now().strftime("%d-%m-%Y")
    filename = f"GOG_detailed_{file_timestamp}.csv"
    # Ensure headers are written only once
    file_exists = False
    try:
        with open(filename, "r", encoding="utf-8") as f:
            file_exists = True
    except FileNotFoundError:
        pass




   
    #filename = f"GOG_detailed_{file_timestamp}.csv"
    with open(filename, "a", newline="", encoding="utf-8") as f:
        fieldnames = ["Name","supplier","SKU", "URL","status", "Price", "PTA", "JHB", "CPT","SOH", "Timestamp"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()  # write column names once

        writer.writerow({
            "Name": item,
            "supplier":"Get Off Grid",
            "SKU":sku,
            "Price":price,
            "PTA": pta_qty,
            "JHB": jhb_qty,
            "CPT": cpt_qty,
            "SOH":cpt_qty+jhb_qty+pta_qty,
            "status":status,
            "Timestamp":timestamp,
            "URL": url
            
        })




def clean_stock(stock_str):
    """Extracts the leading number and ignores any trailing descriptive text."""
    if pd.isna(stock_str):
        return 0
        
    # Convert to string and clean up
    s = str(stock_str).strip()
        
    # Split by space to get the first part (the number)
    # e.g., "1 In Stock..." becomes ["1", "In", "Stock..."]
    parts = s.split(' ')
    first_part = parts[0]
        
    # Extract the number from the first part
    match = re.search(r'-?\d+', first_part)
        
    if match:
        val = int(match.group())
        # Ensure no negative stock
        return max(0, val)
        
    return 0
async def existing_scraper_one(browser_or_context, url: str) -> dict:
    """Scraper logic supporting both standard Browser instances and BrowserContext (persistent sessions)."""
    
    # 1. Handle incoming type dynamically
    if hasattr(browser_or_context, "new_context"):
        # It's a Browser instance -> create a context
        context = await browser_or_context.new_context()
        should_close_context = True
    else:
        # It's already a BrowserContext (e.g. persistent context)
        context = browser_or_context
        should_close_context = False

    page = await context.new_page()


    # p = pd.read_csv("GOG_detailed_12-08-2026.csv")
    # P = p[p['status'] == 'success']

    # dict_dataa = {"scraped_products": P}
    # json_str = P.to_json(orient="records")
    # return {"scraped_count": json_str, "failed_count": 0,"result": "success","Product_count": len(P)}

    #return {P}
    ret_products = []
    sitename = "GOG"
    target_url = "https://gog.store.unleashedsoftware.com/Home"

    try:
        await page.goto(target_url, wait_until="domcontentloaded")
        print(f"✅ Reused login for {sitename}, page title:", await page.title())

        csv_path = os.path.join(BASE_DIR, "GOG-with_sku-2.csv")
        all_products = pd.read_csv(csv_path)
        prods = all_products[['name', 'alt_name', 'sku']]

        prods_page = "https://gog.store.unleashedsoftware.com/products;page=1"
        await page.goto(prods_page, wait_until="domcontentloaded")

        scrape_products = 0
        failed_scrape_products = 0

        def normalize_qty(qty: str):
            if not qty or qty.lower() == "chat with sales":
                return "0"
            return qty.replace(" In Stock", "").strip()

        for ii in range(len(prods)):
            await asyncio.sleep(2)  # Use asyncio.sleep, NOT time.sleep
            await page.goto(prods_page, wait_until="domcontentloaded")
            await page.wait_for_selector("#searchField", timeout=30000)

            pro = str(prods['name'][ii])
            alt_name = str(prods['alt_name'][ii])
            sku = prods['sku'][ii]
            if pd.isna(sku):
                continue

            cleaned = " ".join(pro.split())

            #await page.pause()  # Pause for debugging if needed
            search_input = page.locator("#searchField")

            if str(alt_name) == "nan":
                desired_item = cleaned
                await search_input.fill(cleaned)
                print(f"Product: {ii + 1} of {len(prods)} | Searching for: {cleaned}")
            else:
                desired_item = alt_name
                await search_input.fill(alt_name)
                print(f"Product: {ii + 1} of {len(prods)} | Searching for: {alt_name}")
            await asyncio.sleep(2)
            await page.keyboard.press("Enter")
            await asyncio.sleep(2)

            try:
                if await page.locator("text=No products found").count() > 0:
                    failed_scrape_products += 1
                    append_product_to_csv(desired_item, "", 0, 0, 0, 0, sku, "failed")
                    print("No products found. Skipping...")
                    continue

                await page.wait_for_selector(".card-title", timeout=60000)
                products = page.locator(".card-title")
                count = await products.count()
                print(f"Found {count} products")

                if count == 1:
                    await products.nth(0).click()
                    await asyncio.sleep(5)

                    await page.wait_for_selector("div.price-tag span span", timeout=60000)

                    while await page.locator("text=Fetching prices").count() > 0:
                        print("Fetching prices...")
                        await asyncio.sleep(5)

                    price_text = await page.locator("div.price-tag span span").nth(0).inner_text()
                    price_parts = price_text.split()

                    clean_P = "0"
                    numeric_price = 0.0
                    try:
                        clean_P = price_parts[0].replace(",", "")
                        numeric_price = float(clean_P)
                    except Exception as e:
                        print(f"Price parsing error: {e}")

                    cpt_raw = await page.locator("div.soh-table-container table tr td").nth(1).inner_text()
                    pta_raw = await page.locator("div.soh-table-container table tr td").nth(3).inner_text()
                    jhb_raw = await page.locator("div.soh-table-container table tr td").nth(5).inner_text()

                    cpt_qty = normalize_qty(cpt_raw)
                    pta_qty = normalize_qty(pta_raw)
                    jhb_qty = normalize_qty(jhb_raw)

                    product_url = page.url
                    status = "success" if numeric_price > 0 else "failed"

                    scrape_products += 1
                    append_product_to_csv(pro, product_url, clean_P, clean_stock(pta_qty), clean_stock(jhb_qty), clean_stock(cpt_qty), sku, status)

                    ret_products.append({
                        "name": pro,
                        "url": product_url,
                        "price": clean_P,
                        "pta_qty": clean_stock(pta_qty),
                        "jhb_qty": clean_stock(jhb_qty),
                        "cpt_qty": clean_stock(cpt_qty),
                        "sku": sku,
                        "status": status
                    })

                else:
                    for i in range(count):
                        title = (await products.nth(i).inner_text()).strip()
                        normalized_title = re.sub(r"\s+", " ", title).lower()
                        normalized_item = re.sub(r"\s+", " ", desired_item).lower()
                        print(f"searching for {normalized_item}, found:{normalized_title}")
                        if normalized_item in normalized_title:
                            print(f"✅ Found desired item at position {i+1}")
                            await products.nth(i).click()
                            await asyncio.sleep(5)
                            await page.wait_for_selector("div.price-tag span span", timeout=60000)

                            while await page.locator("text=Fetching prices").count() > 0:
                                print("Fetching prices")
                            
                            await asyncio.sleep(10)
                            price = (
                                await page.locator("div.price-tag span span")
                                .nth(0)
                                .inner_text()
                                .replace("/ EA ZAR excl. tax", "")
                                .strip()
                            )

                            p = price.split()
                            print(f"price str: {p}")
                           
                            clean_P = price.replace("/ EA ZAR excl. tax", "").strip()
                            clean_P = price.replace(" EA ZAR excl. tax", "").strip()
                            clean_P = clean_P.replace(",","")



                            def normalize_qty(qty):
                                return 0 if qty.lower() == "chat with sales" else qty.replace(" In Stock", "").strip()

                            cpt_qty = normalize_qty(await page.locator("div.soh-table-container table tr td").nth(1).inner_text())
                            pta_qty = normalize_qty(await page.locator("div.soh-table-container table tr td").nth(3).inner_text())
                            jhb_qty = normalize_qty(await page.locator("div.soh-table-container table tr td").nth(5).inner_text())
                        
                            locacion = [cpt_qty,jhb_qty,pta_qty]

                        
                        
                        
                            numeric_price = float(price.replace(",",""))
                            status = ""
                            try:
                                if numeric_price > 0:
                                    status = "success"
                            except:
                                status = "failed"



                            



                            product_url = await page.url
                            scrape_products = scrape_products + 1
                            append_product_to_csv(pro, product_url, clean_P, clean_stock(pta_qty), clean_stock(jhb_qty), clean_stock(cpt_qty),sku,status)
                            print(f"✅ Found desired item: {pro} at position {ii}")
                            print(f"Price: {clean_P}, PTA: {pta_qty}, JHB: {jhb_qty}, CPT: {cpt_qty}")


                            await page.go_back()
                            break



                    print(f"✅ Found item: {pro} | Price: {clean_P}, PTA: {pta_qty}, JHB: {jhb_qty}, CPT: {cpt_qty}")
                    await page.go_back()

            except Exception as e:
                print(f"⚠️ Error scraping product '{cleaned}': {e}")
                continue
    except Exception as e:
           print(f"⚠️ Error scraping product '{cleaned}': {e}")
    


    finally:
        await page.close()
        if should_close_context:
            await context.close()


        reet_products = pd.DataFrame(ret_products)
        #df = [reet_products.replace([np.inf, -np.inf], np.nan) for reet_product in reet_products]

        # Option 1: Convert to dict with None (JSON-safe nulls)
        #data_dict = df.where(pd.notnull(df), None).to_dict(orient="records")

        # Option 2: Output JSON string directly using pandas
        json_str = reet_products.to_json(orient="records")
        #dict_data = ret_products.to_dict(orient="records")
        dict_dataa = {"scraped_products": json_str}
    return {"scraped_count": dict_dataa, "failed_count": failed_scrape_products}

async def existing_scraper_two(browser: Browser, product_id: str) -> dict:
    """Your pre-existing scraper logic for Site B."""
    context = await browser.new_context()
    page = await context.new_page()
    try:
        await page.goto(f"https://example.com/item/{product_id}", timeout=30000)
        price = await page.locator(".price").inner_text()
        return {"product_id": product_id, "price": price}
    finally:
        await context.close()


# ==========================================
# 2. ARQ TASK WRAPPERS (Safety Guardrails)
# ==========================================


async def hello_wild(dat=None):
    #await
    wb = pd.read_excel(r"C:\Users\User\source\repos\my_agent\ShopifyPriceBook - USE THIS ONE.xlsx")

    wb.dropna(subset=['Product SKU'],inplace=True)

    sheet = wb.to_json(orient="records")


    print(sheet)
    
   

    sleep(10)
    return {"All_Products": sheet,"status": "completed"}


async def task_run_scraper_one(ctx: dict, url: str) -> dict:
    user_data_path = ctx.get("user_data_path", "./user_sessions/default")
    
    # Launch persistent context per task to ensure clean lifecycle
    async with async_playwright() as p:
        try:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_path,
                headless=False
            )
            
            # Patch target if existing_scraper_one expects browser.new_context()
            if not hasattr(context, "new_context"):
                context.new_context = lambda **kwargs: _async_return(context)

            data = await existing_scraper_one(context, url)



            print(f"✅ Scraper One completed for URL: {url} | Data: {data}")
            
            return {"status": "success", "data": data, "url": url}

        except Exception as e:
            print(f"Error in task_run_scraper_one: {e}")
            return {"status": "error", "error": str(e), "url": url}
        finally:
            if 'context' in locals():
                await context.close()

async def _async_return(val):
    return val


async def task_run_scraper_two(ctx: dict, product_id: str) -> dict:
    """Safe wrapper for Scraper 2."""
    try:
        browser: Browser = ctx["browser"]
        data = await existing_scraper_two(browser, product_id)
        return {"status": "success", "data": "data"}
    except Exception as e:
        return {"status": "error", "error": str(e), "product_id": product_id}


# ==========================================
# 3. WORKER LIFECYCLE & CONFIGURATION
# ==========================================

async def startup(ctx: dict):
    # Launch browser once when worker boots up
    p = await async_playwright().start()
    browser = await p.chromium.launch(
        headless=False,
        args=["--no-sandbox", "--disable-dev-shm-usage"]  # Critical for server stability
    )
    ctx["playwright"] = p
    ctx["browser"] = browser


async def shutdown(ctx: dict):
    # Clean shutdown of browser resources
    if "browser" in ctx:
        await ctx["browser"].close()
    if "playwright" in ctx:
        await ctx["playwright"].stop()


class WorkerSettings:
    # 1. Register only the top-level task functions
    functions = [
        task_run_scraper_one,
        hello_wild,
        #task_run_scraper_two,
    ]
    
    # 2. Prevent RAM explosion by capping simultaneous pages
    max_jobs = 5  # Adjust based on server RAM (Playwright uses ~100MB-200MB per page)
    
    # 3. Task timeouts (kill runaway tasks after 60 seconds)
    job_timeout = 60000 
    
    # 4. Global retry rules
    max_tries = 3
    
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host="127.0.0.1", port=6379)