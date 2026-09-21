from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import Optional, List


import sys
from pathlib import Path
from datetime import datetime
#============================================================================
#================         CRITICAL          =================================
#================         CRITICAL          =================================
#================         CRITICAL          =================================
#============================================================================

# Add the directory 2 levels up to sys.path

parent_dir = Path(__file__).resolve().parents[1]
sys.path.append(str(parent_dir))

from skills import Windows_notifications

#============================================================================
#================         CRITICAL          =================================
#================         CRITICAL          =================================
#================         CRITICAL          =================================
#============================================================================

app = FastAPI()


#===== ORDER SCHEMA
#===== ORDER SCHEMA
#===== ORDER SCHEMA
#===== ORDER SCHEMA

class OrderLineItem(BaseModel):
    line_item_id: int = Field(..., alias="id")
    product_id: Optional[int] = None
    variant_id: Optional[int] = None
    title: str
    quantity: int = 1
    price: float = 0.0
    sku: Optional[str] = None

# 2. Shipping/Billing Address structure
class Address(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    address1: Optional[str] = None
    city: Optional[str] = None
    zip_code: Optional[str] = Field(None, alias="zip")
    country: Optional[str] = None

# 3. Customer summary
class Customer(BaseModel):
    customer_id: int = Field(..., alias="id")
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None

#====== Order payload schema
#====== Order payload schema
#====== Order payload schema
#====== Order payload schema


class OrderWebhookPayload(BaseModel):
    order_id: int = Field(..., alias="id")  # Maps JSON "id" to order_id
    order_number: str                       # e.g. "#1001"
    email: Optional[str] = None
    currency: str = "USD"
    total_price: float = 0.0
    subtotal_price: float = 0.0
    financial_status: Optional[str] = None  # e.g., "paid", "pending"
    fulfillment_status: Optional[str] = "unfulfilled"
    created_at: Optional[datetime] = None  # Pydantic parses ISO date strings automatically!
    
    # Nested relationships
    customer: Optional[Customer] = None
    shipping_address: Optional[Address] = None
    line_items: List[OrderLineItem] = []
@app.post("/webhooks/order-created", status_code=201)
async def handle_order_created(payload: OrderWebhookPayload):
    # Access order metadata directly
    print(f"📦 New Order Received: #{payload.order_number} (ID: {payload.order_id})")
    print(f"   Total: {payload.total_price} {payload.currency} | Status: {payload.financial_status}")
    
    # Customer info
    if payload.customer:
        print(f"   Customer: {payload.customer.first_name} {payload.customer.last_name} ({payload.email})")
        
    # Shipping destination
    if payload.shipping_address:
        addr = payload.shipping_address
        print(f"   Ship To: {addr.city}, {addr.country}")

    # Process items in the order
    print("   Line Items:")
    for item in payload.line_items:
        print(f"     - {item.quantity}x {item.title} (SKU: {item.sku}) @ ${item.price}")

    # Trigger inventory reductions, send confirmation emails, or save to DB here...

    return {
        "status": "success", 
        "order_id": payload.order_id,
        "items_processed": len(payload.line_items)
    }

#===== CUSTOMER SCHEMA
#===== CUSTOMER SCHEMA
#===== CUSTOMER SCHEMA

# 1. Define schema for nested product variants/inventory if present
class ProductVariant(BaseModel):
    variant_id: Optional[int] = Field(None, alias="id")
    sku: Optional[str] = None
    price: Optional[float] = 0.0
    inventory_quantity: Optional[int] = 0

# 2. Define top-level Product payload schema
class ProductWebhookPayload(BaseModel):
    product_id: int = Field(..., alias="id")  # Maps JSON "id" to product_id
    title: str
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    variants: Optional[List[ProductVariant]] = []

@app.post("/webhooks/product-update")
async def handle_product_update(payload: ProductWebhookPayload):
    # Access validated attributes directly
    # print(f"Product ID: {payload.product_id}")
    # print(f"Title: {payload.title}")
    # print(f"Vendor: {payload.vendor}")
    print(f"Product:\n  {payload}")
    # Loop through variants
    for variant in payload.variants:
        print(f"  -> Variant SKU: {variant.sku} | Quantity: {variant.inventory_quantity}")

    # Process database updates or background jobs here...
        if variant.inventory_quantity == 0:
            Windows_notifications.send_notification("Product updated", f"Product {payload.title} has been updated, and is now out of stock.")

    return {"status": "success", "product_id": payload.product_id}