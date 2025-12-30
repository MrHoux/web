from app import create_app
from app.extensions import db
from app.models import (
    Category,
    User,
    UserRole,
    MerchantProfile,
    Product,
    ProductStatus,
    ProductCategory,
)

app = create_app()

with app.app_context():
    # Create initial categories
    categories_data = [
        {"name": "Electronics", "slug": "electronics"},
        {"name": "Clothing", "slug": "clothing"},
        {"name": "Food", "slug": "food"},
        {"name": "Books", "slug": "books"},
        {"name": "Home", "slug": "home"},
        {"name": "Sports", "slug": "sports"},
        {"name": "Beauty", "slug": "beauty"},
        {"name": "Toys", "slug": "toys"},
    ]

    categories_dict = {}
    for cat_data in categories_data:
        existing = Category.query.filter_by(slug=cat_data["slug"]).first()
        if not existing:
            category = Category(
                name=cat_data["name"], slug=cat_data["slug"], is_active=True
            )
            db.session.add(category)
            db.session.flush()
            categories_dict[cat_data["slug"]] = category
            print(f"Created category: {cat_data['name']}")
        else:
            categories_dict[cat_data["slug"]] = existing

    # Create admin account (if not exists)
    admin_email = "admin@example.com"
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(email=admin_email, role=UserRole.ADMIN)
        admin.set_password("admin123")
        db.session.add(admin)
        print(f"Created admin account: {admin_email} / admin123")

    # Create merchants and products
    merchants_data = [
        {
            "email": "merchant1@example.com",
            "shop_name": "TechStore Pro",
            "products": [
                {
                    "title": "Wireless Bluetooth Headphones",
                    "description": (
                        "High-quality wireless headphones with noise "
                        "cancellation"
                    ),
                    "price": 99.99,
                    "stock": 50,
                    "categories": ["electronics"],
                },
                {
                    "title": "Smartphone Case",
                    "description": "Protective case for latest smartphones",
                    "price": 19.99,
                    "stock": 100,
                    "categories": ["electronics"],
                },
                {
                    "title": "USB-C Cable",
                    "description": "Fast charging USB-C cable, 2m length",
                    "price": 12.99,
                    "stock": 200,
                    "categories": ["electronics"],
                },
            ],
        },
        {
            "email": "merchant2@example.com",
            "shop_name": "Fashion Hub",
            "products": [
                {
                    "title": "Cotton T-Shirt",
                    "description": "Comfortable 100% cotton t-shirt",
                    "price": 24.99,
                    "stock": 150,
                    "categories": ["clothing"],
                },
                {
                    "title": "Denim Jeans",
                    "description": "Classic blue denim jeans",
                    "price": 59.99,
                    "stock": 80,
                    "categories": ["clothing"],
                },
                {
                    "title": "Running Shoes",
                    "description": "Lightweight running shoes for athletes",
                    "price": 89.99,
                    "stock": 60,
                    "categories": ["clothing", "sports"],
                },
            ],
        },
        {
            "email": "merchant3@example.com",
            "shop_name": "Book Paradise",
            "products": [
                {
                    "title": "Programming Python Guide",
                    "description": "Complete guide to Python programming",
                    "price": 39.99,
                    "stock": 75,
                    "categories": ["books"],
                },
                {
                    "title": "Web Development Handbook",
                    "description": "Modern web development techniques",
                    "price": 44.99,
                    "stock": 50,
                    "categories": ["books"],
                },
                {
                    "title": "Fiction Novel Collection",
                    "description": "Bestselling fiction novels set",
                    "price": 29.99,
                    "stock": 90,
                    "categories": ["books"],
                },
            ],
        },
        {
            "email": "merchant4@example.com",
            "shop_name": "Home Essentials",
            "products": [
                {
                    "title": "Coffee Maker",
                    "description": "Automatic drip coffee maker",
                    "price": 79.99,
                    "stock": 40,
                    "categories": ["home"],
                },
                {
                    "title": "Kitchen Knife Set",
                    "description": "Professional 6-piece knife set",
                    "price": 129.99,
                    "stock": 30,
                    "categories": ["home"],
                },
                {
                    "title": "Bed Sheet Set",
                    "description": "Premium cotton bed sheet set",
                    "price": 49.99,
                    "stock": 70,
                    "categories": ["home"],
                },
            ],
        },
        {
            "email": "merchant5@example.com",
            "shop_name": "Sports World",
            "products": [
                {
                    "title": "Yoga Mat",
                    "description": "Non-slip yoga mat for workouts",
                    "price": 34.99,
                    "stock": 100,
                    "categories": ["sports"],
                },
                {
                    "title": "Dumbbell Set",
                    "description": "Adjustable dumbbell set 2x20kg",
                    "price": 149.99,
                    "stock": 25,
                    "categories": ["sports"],
                },
                {
                    "title": "Tennis Racket",
                    "description": "Professional tennis racket",
                    "price": 119.99,
                    "stock": 35,
                    "categories": ["sports"],
                },
            ],
        },
        {
            "email": "merchant6@example.com",
            "shop_name": "Beauty Boutique",
            "products": [
                {
                    "title": "Face Moisturizer",
                    "description": "Hydrating face moisturizer",
                    "price": 29.99,
                    "stock": 120,
                    "categories": ["beauty"],
                },
                {
                    "title": "Lipstick Set",
                    "description": "5-color lipstick collection",
                    "price": 19.99,
                    "stock": 90,
                    "categories": ["beauty"],
                },
                {
                    "title": "Sunscreen SPF 50",
                    "description": "High protection sunscreen",
                    "price": 16.99,
                    "stock": 150,
                    "categories": ["beauty"],
                },
            ],
        },
        {
            "email": "merchant7@example.com",
            "shop_name": "Toy Kingdom",
            "products": [
                {
                    "title": "LEGO Building Set",
                    "description": "Creative building blocks set",
                    "price": 49.99,
                    "stock": 60,
                    "categories": ["toys"],
                },
                {
                    "title": "Board Game Collection",
                    "description": "Family board games pack",
                    "price": 39.99,
                    "stock": 45,
                    "categories": ["toys"],
                },
                {
                    "title": "Remote Control Car",
                    "description": "Fast remote control car",
                    "price": 59.99,
                    "stock": 55,
                    "categories": ["toys"],
                },
            ],
        },
        {
            "email": "merchant8@example.com",
            "shop_name": "Gourmet Foods",
            "products": [
                {
                    "title": "Organic Honey",
                    "description": "Pure organic honey 500g",
                    "price": 14.99,
                    "stock": 200,
                    "categories": ["food"],
                },
                {
                    "title": "Premium Coffee Beans",
                    "description": "Arabica coffee beans 1kg",
                    "price": 24.99,
                    "stock": 100,
                    "categories": ["food"],
                },
                {
                    "title": "Dark Chocolate Box",
                    "description": "Artisan dark chocolate collection",
                    "price": 19.99,
                    "stock": 130,
                    "categories": ["food"],
                },
            ],
        },
    ]

    for merchant_data in merchants_data:
        merchant_user = User.query.filter_by(
            email=merchant_data["email"]
        ).first()
        if not merchant_user:
            merchant_user = User(
                email=merchant_data["email"], role=UserRole.MERCHANT
            )
            merchant_user.set_password("merchant123")
            db.session.add(merchant_user)
            db.session.flush()

            # Create merchant profile
            profile = MerchantProfile(
                user_id=merchant_user.id,
                shop_name=merchant_data["shop_name"],
                description=(
                    f'{merchant_data["shop_name"]} - '
                    "Quality products for you"
                ),
            )
            db.session.add(profile)
            print(
                "Created merchant: %s / merchant123 - %s"
                % (merchant_data["email"], merchant_data["shop_name"])
            )

            # Create products for this merchant
            for product_data in merchant_data["products"]:
                product = Product(
                    merchant_id=merchant_user.id,
                    title=product_data["title"],
                    description=product_data["description"],
                    price=product_data["price"],
                    stock=product_data["stock"],
                    status=ProductStatus.ACTIVE,
                )
                db.session.add(product)
                db.session.flush()

                # Add categories to product
                for cat_slug in product_data["categories"]:
                    if cat_slug in categories_dict:
                        pc = ProductCategory(
                            product_id=product.id,
                            category_id=categories_dict[cat_slug].id,
                        )
                        db.session.add(pc)

                print(f"  Created product: {product_data['title']}")

    db.session.commit()
    print("Data initialization completed!")
