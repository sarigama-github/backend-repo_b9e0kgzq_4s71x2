"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- Order -> "order" collection
- Cart -> "cart" collection
"""

from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List

class Product(BaseModel):
    """
    Products collection schema
    Collection name: "product" (lowercase of class name)
    """
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: str = Field(..., description="Product category")
    image: Optional[str] = Field(None, description="Image URL")
    in_stock: bool = Field(True, description="Whether product is in stock")
    rating: Optional[float] = Field(4.5, ge=0, le=5, description="Average rating")

class CartItem(BaseModel):
    session_id: str = Field(..., description="Anonymous cart/session identifier")
    product_id: str = Field(..., description="Product ObjectId as string")
    quantity: int = Field(1, ge=1, description="Quantity of the product")

class OrderItem(BaseModel):
    product_id: str
    title: str
    price: float
    quantity: int
    subtotal: float

class Order(BaseModel):
    session_id: str
    customer_name: str
    customer_email: EmailStr
    customer_address: str
    items: List[OrderItem]
    total: float
