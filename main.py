import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, CartItem, Order, OrderItem

app = FastAPI(title="E-commerce API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Utilities

def to_str_id(doc: dict):
    if not doc:
        return doc
    d = {**doc}
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    return d


def get_product_or_404(product_id: str) -> dict:
    try:
        _id = ObjectId(product_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product id")
    prod = db["product"].find_one({"_id": _id})
    if not prod:
        raise HTTPException(status_code=404, detail="Product not found")
    return prod


@app.get("/")
def read_root():
    return {"message": "E-commerce Backend is running"}


@app.get("/api/products")
def list_products(category: Optional[str] = None, limit: int = Query(50, ge=1, le=100)):
    filt = {"category": category} if category else {}
    products = db["product"].find(filt).limit(limit)
    return [to_str_id(p) for p in products]


class SeedRequest(BaseModel):
    force: bool = False


@app.post("/api/products/seed")
def seed_products(payload: SeedRequest):
    count = db["product"].count_documents({})
    if count > 0 and not payload.force:
        return {"inserted": 0, "message": "Products already exist"}

    if payload.force:
        db["product"].delete_many({})

    sample_products = [
        {
            "title": "Classic Tee",
            "description": "Soft cotton unisex t-shirt",
            "price": 19.99,
            "category": "Apparel",
            "image": "https://images.unsplash.com/photo-1520975916090-3105956dac38?q=80&w=800&auto=format&fit=crop",
            "in_stock": True,
            "rating": 4.6,
        },
        {
            "title": "Minimal Backpack",
            "description": "Lightweight everyday backpack",
            "price": 49.0,
            "category": "Bags",
            "image": "https://images.unsplash.com/photo-1519681393784-d120267933ba?q=80&w=800&auto=format&fit=crop",
            "in_stock": True,
            "rating": 4.4,
        },
        {
            "title": "Wireless Earbuds",
            "description": "Noise-isolating Bluetooth earbuds",
            "price": 59.99,
            "category": "Electronics",
            "image": "https://images.unsplash.com/photo-1518448059646-51f7ebf92613?q=80&w=800&auto=format&fit=crop",
            "in_stock": True,
            "rating": 4.2,
        },
        {
            "title": "Ceramic Mug",
            "description": "12oz matte finish mug",
            "price": 12.5,
            "category": "Home",
            "image": "https://images.unsplash.com/photo-1525385133512-2f3bdd039054?q=80&w=800&auto=format&fit=crop",
            "in_stock": True,
            "rating": 4.8,
        },
    ]
    res = db["product"].insert_many(sample_products)
    return {"inserted": len(res.inserted_ids)}


@app.post("/api/cart/add")
def add_to_cart(item: CartItem):
    # Ensure product exists
    _ = get_product_or_404(item.product_id)
    # Upsert cart item by session+product
    existing = db["cart"].find_one({"session_id": item.session_id, "product_id": item.product_id})
    if existing:
        new_qty = int(existing.get("quantity", 1)) + int(item.quantity)
        if new_qty <= 0:
            db["cart"].delete_one({"_id": existing["_id"]})
            return {"status": "removed"}
        db["cart"].update_one({"_id": existing["_id"]}, {"$set": {"quantity": new_qty}})
        updated = db["cart"].find_one({"_id": existing["_id"]})
        return to_str_id(updated)
    else:
        if item.quantity <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")
        doc_id = create_document("cart", item)
        created = db["cart"].find_one({"_id": ObjectId(doc_id)})
        return to_str_id(created)


@app.get("/api/cart")
def get_cart(session_id: str = Query(...)):
    items = list(db["cart"].find({"session_id": session_id}))
    # hydrate with product info and totals
    enriched = []
    total = 0.0
    for it in items:
        prod = get_product_or_404(it["product_id"]) if it.get("product_id") else None
        price = float(prod.get("price", 0.0)) if prod else 0.0
        qty = int(it.get("quantity", 1))
        subtotal = qty * price
        total += subtotal
        enriched.append({
            "id": str(it.get("_id")),
            "product_id": it.get("product_id"),
            "quantity": qty,
            "title": prod.get("title") if prod else None,
            "price": price,
            "image": prod.get("image") if prod else None,
            "subtotal": round(subtotal, 2),
        })
    return {"items": enriched, "total": round(total, 2)}


@app.delete("/api/cart/cleanup")
def cleanup_cart(session_id: str = Query(...)):
    # Remove any items with quantity <= 0 just in case
    result = db["cart"].delete_many({"session_id": session_id, "quantity": {"$lte": 0}})
    return {"deleted": result.deleted_count}


class CheckoutRequest(BaseModel):
    session_id: str
    customer_name: str
    customer_email: str
    customer_address: str


@app.post("/api/checkout")
def checkout(payload: CheckoutRequest):
    # Load cart
    cart_data = get_cart(payload.session_id)
    if len(cart_data["items"]) == 0:
        raise HTTPException(status_code=400, detail="Cart is empty")
    # Build order
    order_items: List[OrderItem] = []
    for it in cart_data["items"]:
        order_items.append(OrderItem(
            product_id=it["product_id"],
            title=it.get("title") or "",
            price=float(it.get("price") or 0.0),
            quantity=int(it.get("quantity") or 1),
            subtotal=float(it.get("subtotal") or 0.0),
        ))
    order = Order(
        session_id=payload.session_id,
        customer_name=payload.customer_name,
        customer_email=payload.customer_email,
        customer_address=payload.customer_address,
        items=order_items,
        total=float(cart_data["total"]),
    )
    order_id = create_document("order", order)
    # clear cart
    db["cart"].delete_many({"session_id": payload.session_id})
    return {"order_id": order_id}


@app.get("/api/orders")
def list_orders(session_id: str = Query(...)):
    orders = db["order"].find({"session_id": session_id}).sort("created_at", -1)
    result = []
    for o in orders:
        out = to_str_id(o)
        return_fields = ["session_id", "customer_name", "customer_email", "customer_address", "items", "total", "created_at"]
        out = {k: out.get(k) for k in ["id"] + return_fields}
        result.append(out)
    return result


@app.get("/api/hello")
def hello():
    return {"message": "Hello from the backend API!"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
