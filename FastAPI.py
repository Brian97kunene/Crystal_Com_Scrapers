from fastapi import FastAPI, HTTPException ,Request, status

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl
from arq import create_pool
from arq.connections import RedisSettings, ArqRedis
from contextlib import asynccontextmanager
import pandas as pd 
from typing import Optional, Dict, Any
from pydantic import BaseModel
from arq.jobs import Job

gog = pd.read_csv("all_sheet_products.csv")

# App Lifespan to handle Redis connection pool
redis_pool: ArqRedis = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global redis_pool
    redis_pool = await create_pool(RedisSettings(host="127.0.0.1", port=6379))
    yield
    await redis_pool.close()

app = FastAPI(lifespan=lifespan)
class InventoryLevelPayload(BaseModel):
    inventory_item_id: Optional[int] = None
    location_id: Optional[int] = None
    available: Optional[int] = None
    updated_at: Optional[str] = None
    # Flexible container for platform-specific extra fields
    extra_data: Optional[Dict[str, Any]] = None

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173","http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

class ScrapeRequest(BaseModel):
    url: str


@app.post("/api/Shopify_hook", status_code=202)
async def web_hook(request: Request):
    try:
        # Read raw JSON body
        payload = await request.json()
        
        # Extract key inventory properties
        item_id = payload.get("inventory_item_id") or payload.get("id")
        available = payload.get("available") or payload.get("available_adjustment")
        location_id = payload.get("location_id")
        
        print(f"[Webhook Received] Item: {item_id} | Location: {location_id} | Available: {available}")

        # TODO: Offload heavy processing (e.g., updating database/Redis) to a background task
        
        # Return 200 OK quickly to acknowledge receipt
        return {"status": "success", "message": "Inventory webhook processed"}
        
    except Exception as e:
        print(f"Error parsing webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid webhook payload"
        )


@app.post("/api/GOG_Scrape", status_code=202)
async def enqueue_scrape(payload: ScrapeRequest):
    # Enqueue task into Redis
    job = await redis_pool.enqueue_job("task_run_scraper_one", str(payload.url))
    
    print(f"Job enqueued: {job.job_id}")
    return {"job_id": job.job_id, "status": "queued"}


@app.get("/api/GOG_Scrape_Work", status_code=202)
async def enqueue_h_scrape():
    # Enqueue task into Redis
    job = await redis_pool.enqueue_job("hello_wild")
    
    print(f"Job enqueued: {job.job_id}")
    return {"job_id": job.job_id, "status": "in progress"}


@app.get("/api/GOG_Scrape/{job_id}")
async def get_scrape_status(job_id: str):

    #job_id = "c54cbdddf8514de8b394f41e814ef145"
    job = Job(job_id, redis=redis_pool)
    status = await job.status()
    
    result = None
    error_message = None

    if status == "complete":
        try:
            # Safely attempt to get the result
            result = await job.result()
        except Exception as exc:
            # If the job failed during execution, catch it gracefully
            status = "failed"
            error_message = str(exc)
        except Exception as exc:
            status = "failed"
            error_message = f"Unexpected error: {str(exc)}"

    return {
        "job_id": job_id,
        "status": status,
        "result": result,
        "error": error_message
    }


@app.get("/api/GOG_Scrape/all")
async def get_all_scrape_results():
    """
    Fetches all jobs tracked in the 'gog_scrape_jobs' Redis set.
    """
    # 1. Get all stored job IDs
    raw_job_ids = await redis_pool.smembers("gog_scrape_jobs")

    print(raw_job_ids)

    job_ids = [j.decode("utf-8") if isinstance(j, bytes) else j for j in raw_job_ids]

    all_jobs = []

    for j_id in job_ids:
        job = Job(j_id, redis=redis_pool)
        
        status_val = await job.status()
        status_str = status_val.value if hasattr(status_val, "value") else str(status_val)

        res_data = None
        error_message = None

        if status_str == "complete":
            try:
                job_info = await job.info()
                if job_info:
                    res_data = job_info.result
            except JobExecutionFailed as exc:
                status_str = "failed"
                error_message = str(exc)
            except Exception as exc:
                status_str = "failed"
                error_message = str(exc)

        all_jobs.append({
            "job_id": j_id,
            "status": status_str,
            "result": res_data,
            "error": error_message
        })

    return {
        "count": len(all_jobs),
        "jobs": all_jobs
    }



@app.get("/api/scrapee/{sku}")
async def hey_world(sku: str):
    data = gog[gog["Product SKU"] == sku]
    dict_data = data.to_dict(orient="records")
    return {"status": "queued", "data": dict_data}
    
@app.get("/api/getAllJobs")
async def get_all_jobs():
    job_keys = await redis_pool.keys("arq:job:*")
    
    jobs_data = []
    for raw_key in job_keys:
        # Strip the prefix to get the clean job_id
        job_id = raw_key.decode("utf-8").replace("arq:job:", "")
        job = Job(job_id, redis=redis_pool)
        
        status = await job.status()
        info = await job.info()
        
        jobs_data.append({
            "job_id": job_id,
            "status": status,
            "function": info.function if info else None,
            "enqueue_time": info.enqueue_time if info else None,
        })

    print(f"Found {len(jobs_data)} jobs:")
    for j in jobs_data:
        print(j)

    return {"jobs": jobs_data}
    
    