
# POS-DB-Project - Inventory Management System

A complete Point of Sale and Inventory Management System with MySQL backend, developed as a lab project for the Database course at the University of Engineering and Technology (UET), Lahore.

---

## ✨ Features

- 🛍️ **Product Management** (CRUD operations)
- 📦 **Inventory Tracking** with stock alerts
- 💰 **Sales Processing** with receipt generation
- 📊 **Advanced Sales Reporting**
- 📈 **OLAP Analysis** and data cubes
- 🔮 **Demand Forecasting**
- 👥 **Role-based User Management**
- 📅 **Price Change History**

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- MySQL Server 8.0+
- Git (optional)

---

### 🔧 Installation

#### 1. Clone the repository

```bash
git clone https://github.com/debuggerZaKa/POS-DB-Project.git
cd POS-DB-Project
```

#### 2. Install dependencies

```bash
pip install -r requirements.txt
```

#### 3. Create MySQL database

Login to your MySQL server and run:

```sql
CREATE DATABASE se_pos;
```

#### 4. Configure database connection

Edit the `config.py` file if your MySQL credentials are different:

```python
class Config:
    DB_HOST = "localhost"
    DB_USER = "root"
    DB_PASSWORD = "root"
    DB_NAME = "se_pos"
```

---

## 📌 Notes

- Ensure MySQL service is running before starting the application.
- If you use a different host, username, or password, update them in `config.py`.


---

## ❗ License

This project is provided for demonstration purposes only.

**All Rights Reserved.**  
Unauthorized use, reproduction, or distribution of this code is strictly prohibited.


---

## 📧 Contact

Developed by **Tahir Zaka & M.Yahya Khan** 
Email: tahirzaka10@gmail.com

---

