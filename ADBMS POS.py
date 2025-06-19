import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import csv
import openpyxl
import hashlib
import os
import mysql.connector
from mysql.connector import Error

from db_utils import execute_query, create_db_connection
from config import Config

from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.pyplot as plt
from mysql.connector import Error
from tkcalendar import DateEntry

# ----------------------------
# Helper Functions
# ----------------------------

def convert_to_base_unit(quantity, unit):
    """Convert quantity to base unit (grams for weight, milliliters for volume) and return the new unit."""
    if unit == "kg":
        return quantity * 1000, "g"
    elif unit == "g":
        return quantity, "g"
    elif unit == "lbs":
        return quantity * 453.592, "g"
    elif unit == "L":
        return quantity * 1000, "mL"
    elif unit == "mL":
        return quantity, "mL"
    elif unit == "pcs":
        return quantity, "pcs"
    elif unit == "m":
        return quantity, "m"
    else:
        raise ValueError("Unknown unit")

def convert_from_base_unit(quantity, unit):
    """Convert quantity from base unit (grams or milliliters) to the original unit for display."""
    if unit == "g":
        return quantity / 1000, "kg"
    elif unit == "kg":
        return quantity, "kg"
    elif unit == "lbs":
        return quantity / 453.592, "lbs"
    elif unit == "mL":
        return quantity / 1000, "L"
    elif unit == "L":
        return quantity, "L"
    elif unit == "pcs":
        return quantity, "pcs"
    elif unit == "m":
        return quantity, "m"
    else:
        raise ValueError("Unknown unit")

# ----------------------------
# Database Initialization
# ----------------------------

def init_db():
    """Initialize the MySQL database with required tables."""
    # First create the database if it doesn't exist
    try:
        conn = mysql.connector.connect(
            host=Config.DB_HOST,
            user=Config.DB_USER,
            password=Config.DB_PASSWORD
        )
        cursor = conn.cursor()
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {Config.DB_NAME}")
        conn.commit()
        cursor.close()
        conn.close()
    except Error as e:
        print(f"Error creating database: {e}")
        return

    # Now create tables
    conn = create_db_connection()
    if conn is None:
        return

    cursor = conn.cursor()

    try:
        # Create products table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                category VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                stock_level DECIMAL(10, 2) NOT NULL,
                unit VARCHAR(10) NOT NULL
            )
        ''')

        # Create stock_history table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS stock_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                quantity_change DECIMAL(10, 2) NOT NULL,
                unit VARCHAR(10) NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        ''')

        # Create sales table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                quantity DECIMAL(10, 2) NOT NULL,
                sale_price DECIMAL(10, 2) NOT NULL,
                total_amount DECIMAL(10, 2) NOT NULL,
                unit VARCHAR(10) NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        ''')

        # Create users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                tabs TEXT
            )
        ''')


  
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS price_history (
                id INT AUTO_INCREMENT PRIMARY KEY,
                product_id INT NOT NULL,
                old_price DECIMAL(10, 2) NOT NULL,
                new_price DECIMAL(10, 2) NOT NULL,
                changed_by VARCHAR(255) DEFAULT 'system',
                change_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(product_id) REFERENCES products(id)
            )
        ''')


        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS after_price_update
            AFTER UPDATE ON products
            FOR EACH ROW
            BEGIN
                IF OLD.price != NEW.price THEN
                    INSERT INTO price_history 
                    (product_id, old_price, new_price, changed_by)
                    VALUES (
                        OLD.id, 
                        OLD.price, 
                        NEW.price,
                        SUBSTRING_INDEX(USER(), '@', 1) -- Gets MySQL username
                    );
                END IF;
            END;
        """)

        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS validate_product_price_insert
            BEFORE INSERT ON products
            FOR EACH ROW
            BEGIN
                IF NEW.price < 0 THEN
                    SIGNAL SQLSTATE '45000' 
                    SET MESSAGE_TEXT = 'Product price cannot be negative';
                END IF;
                IF NEW.stock_level < 0 THEN
                    SIGNAL SQLSTATE '45000' 
                    SET MESSAGE_TEXT = 'Stock level cannot be negative';
                END IF;
            END;
        """)
        
        # Trigger for UPDATE on products table
        cursor.execute("""
            CREATE TRIGGER IF NOT EXISTS validate_product_price_update
            BEFORE UPDATE ON products
            FOR EACH ROW
            BEGIN
                IF NEW.price < 0 THEN
                    SIGNAL SQLSTATE '45000' 
                    SET MESSAGE_TEXT = 'Product price cannot be negative';
                END IF;
                IF NEW.stock_level < 0 THEN
                    SIGNAL SQLSTATE '45000' 
                    SET MESSAGE_TEXT = 'Stock level cannot be negative';
                END IF;
            END;
        """)

    
        cursor.execute("""
            CREATE OR REPLACE VIEW enhanced_sales_report AS
            SELECT 
                s.id,
                p.name AS product_name,
                s.quantity,
                s.unit,
                s.sale_price,
                s.total_amount,
                s.date,
                SUM(s.total_amount) OVER (PARTITION BY DATE(s.date)) AS daily_total,
                SUM(s.total_amount) OVER (ORDER BY s.date) AS running_total,
                RANK() OVER (PARTITION BY DATE(s.date) ORDER BY s.total_amount DESC) AS daily_rank
            FROM sales s
            JOIN products p ON s.product_id = p.id
            ORDER BY s.date DESC;
        """)




    
        # Check if users table is empty; if so, create a default manager account
        cursor.execute("SELECT COUNT(*) FROM users")
        if cursor.fetchone()[0] == 0:
            default_username = "developer"
            default_password = "developerkey"
            hashed_password = hash_password(default_password)
            
            all_tabs = [
                "Product Management",
                "Inventory Management",
                "Sales Processing",
                "Sales Reports",
                "Billing",
                "User Management"
            ]
            tabs_str = ",".join(all_tabs)
            
            cursor.execute("INSERT INTO users (username, password, role, tabs) VALUES (%s, %s, %s, %s)",
                         (default_username, hashed_password, "manager", tabs_str))
            print(f"Default manager account created. Username: '{default_username}', Password: '{default_password}', Tabs: '{tabs_str}'")

        conn.commit()

    except Error as e:
        print(f"Error initializing database: {e}")
            # Create views
        cursor.execute("""
                CREATE OR REPLACE VIEW low_stock_view AS
                SELECT 
                    p.id, 
                    p.name, 
                    CASE 
                        WHEN p.unit = 'g' THEN ROUND(p.stock_level / 1000, 2)
                        WHEN p.unit = 'mL' THEN ROUND(p.stock_level / 1000, 2)
                        ELSE p.stock_level
                    END AS display_stock,
                    p.unit,
                    p.category,
                    p.price
                FROM products p
                WHERE p.stock_level < (SELECT AVG(stock_level) * 0.3 FROM products)
            """)
            
        cursor.execute("""
                CREATE OR REPLACE VIEW daily_sales_summary AS
                SELECT 
                    DATE(s.date) as sale_date,
                    COUNT(*) as total_transactions,
                    SUM(s.total_amount) as daily_revenue,
                    AVG(s.total_amount) as avg_sale_value,
                    MAX(s.total_amount) as max_sale,
                    MIN(s.total_amount) as min_sale
                FROM sales s
                GROUP BY DATE(s.date)
            """)
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()



# ----------------------------
# Product Management UI
# ----------------------------

class ProductManagementUI:
    def __init__(self, parent):
        self.parent = parent
        self.parent.configure(bg="#f0f0f0")  # Light grey background

        # Configure the grid layout
        self.parent.grid_rowconfigure(0, weight=1)  # Labels & Entry rows
        self.parent.grid_rowconfigure(1, weight=1)
        self.parent.grid_rowconfigure(2, weight=1)
        self.parent.grid_rowconfigure(3, weight=1)
        self.parent.grid_rowconfigure(4, weight=1)
        self.parent.grid_rowconfigure(5, weight=1)  # Buttons row
        self.parent.grid_rowconfigure(6, weight=20)  # Increased weight for Treeview (to stretch fully)
        self.parent.grid_columnconfigure(0, weight=1)
        self.parent.grid_columnconfigure(1, weight=2)
        self.parent.grid_columnconfigure(2, weight=1)

        self.create_widgets()
        self.populate_products()

    def create_widgets(self):
        # Labels and Entry fields
        tk.Label(self.parent, text="Product Name").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.name_entry = tk.Entry(self.parent)
        self.name_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(self.parent, text="Category").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.category_entry = tk.Entry(self.parent)
        self.category_entry.grid(row=1, column=1, padx=10, pady=5)

        tk.Label(self.parent, text="Price").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.price_entry = tk.Entry(self.parent)
        self.price_entry.grid(row=2, column=1, padx=10, pady=5)

        tk.Label(self.parent, text="Stock Level").grid(row=3, column=0, padx=10, pady=5, sticky='w')
        self.stock_entry = tk.Entry(self.parent)
        self.stock_entry.grid(row=3, column=1, padx=10, pady=5)

        tk.Label(self.parent, text="Unit").grid(row=4, column=0, padx=10, pady=5, sticky='w')
        self.unit_entry = ttk.Combobox(self.parent, values=["kg", "g", "lbs", "L", "mL", "pcs", "m"])
        self.unit_entry.grid(row=4, column=1, padx=10, pady=5)

        # Buttons
        button_width = 15  # Set a fixed width for all buttons

        self.add_product_button = tk.Button(self.parent, text="Add Product", bg="#28a745", fg="white", width=button_width, command=self.add_product)
        self.add_product_button.grid(row=1, column=2, padx=3, pady=10)

        self.update_product_button = tk.Button(self.parent, text="Update Product", bg="#007bff", fg="white", width=button_width, command=self.update_product)
        self.update_product_button.grid(row=2, column=2, padx=3, pady=10)

        self.delete_product_button = tk.Button(self.parent, text="Delete Product", bg="#dc3545", fg="white", width=button_width, command=self.delete_product)
        self.delete_product_button.grid(row=4, column=2, padx=3, pady=10)

        # Refresh Button
        self.refresh_button = tk.Button(self.parent, text="Refresh", bg="#6a5acd", fg="white", width=button_width, command=self.populate_products)  # Purple color
        self.refresh_button.grid(row=3, column=2, padx=3, pady=10)

        # Styling the buttons for hover effect
        for button, hover_color in zip(
            [self.add_product_button, self.update_product_button, self.delete_product_button, self.refresh_button],
            ["#218838", "#0056b3", "#c82333", "#5b3f8d"]
        ):
            button.bind("<Enter>", lambda e, b=button, c=hover_color: b.config(bg=c))
            button.bind("<Leave>", lambda e, b=button: b.config(bg=b.cget("bg")))


        # Product List (Treeview)
        style = ttk.Style()
        style.theme_use("clam")  # Use a theme that allows full customization
        style.configure(
            "Treeview",
            background="#2b2b2b",
            foreground="white",
            fieldbackground="#2b2b2b",
            font=("Arial", 12),
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background="#2b2b2b",  # Blackish grey for header
            foreground="white",
            font=("Arial", 14, "bold"),
            borderwidth=0,
        )
        style.map("Treeview.Heading", background=[("active", "#3b3b3b")])  # Hover effect for headers
        style.layout(
            "Treeview",
            [
                ("Treeview.treearea", {"sticky": "nswe"})  # Make the entire block colored
            ]
        )

        columns = ("ID", "Name", "Category", "Unit Price", "Stock Level")
        self.tree = ttk.Treeview(self.parent, columns=columns, show='headings', style="Treeview", height=20)  # Increased height for more rows
        for col in columns:
            self.tree.heading(col, text=col, anchor='w')
            self.tree.column(col, width=150 if col in ["Name", "Category", "Unit"] else 100)
        self.tree.grid(row=6, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')

        # Configure grid weights for responsiveness
        self.parent.grid_rowconfigure(7, weight=1)
        self.parent.grid_columnconfigure(2, weight=1)

        # Scrollbar for the Treeview
        scrollbar = ttk.Scrollbar(self.parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=6, column=3, sticky='ns')

        # Bind the treeview select
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

    def populate_products(self):
        # Clear the current entries in the treeview
        for row in self.tree.get_children():
            self.tree.delete(row)

        # Connect to the database and fetch products
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM products")
            products = cursor.fetchall()

            # Insert products into the treeview
            for product in products:
                id, name, category, price, stock_level, unit = product
                # Convert stock level to display in the original unit
                displayed_stock, display_unit = convert_from_base_unit(stock_level, unit)
                self.tree.insert("", "end", values=(id, name, category, price, f"{displayed_stock:.2f} {display_unit}"))

        except Error as e:
            messagebox.showerror("Database Error", f"Error fetching products: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def on_tree_select(self, event):
    # Get selected item
        selected_item = self.tree.selection()
        if selected_item:
            item_values = self.tree.item(selected_item, 'values')
            
            # Clear all entry fields first
            self.clear_entries()
            
            # Fill entry fields with selected product details
            try:
                # Product Name
                if len(item_values) > 1:
                    self.name_entry.insert(0, item_values[1])
                
                # Category
                if len(item_values) > 2:
                    self.category_entry.insert(0, item_values[2])
                
                # Price
                if len(item_values) > 3:
                    self.price_entry.insert(0, item_values[3])
                
                # Stock Level and Unit (handled together)
                if len(item_values) > 4:
                    stock_display = item_values[4]
                    # Split "5.00 kg" into ["5.00", "kg"]
                    stock_parts = stock_display.split()
                    
                    # Quantity part (first part)
                    if len(stock_parts) > 0:
                        self.stock_entry.insert(0, stock_parts[0])
                    
                    # Unit part (second part if exists)
                    if len(stock_parts) > 1:
                        self.unit_entry.set(stock_parts[1])
                    else:
                        # If no unit in display, try to get from database
                        product_id = item_values[0]
                        conn = create_db_connection()
                        if conn:
                            try:
                                cursor = conn.cursor()
                                cursor.execute("SELECT unit FROM products WHERE id = %s", (product_id,))
                                result = cursor.fetchone()
                                if result:
                                    self.unit_entry.set(result[0])
                            except Error as e:
                                print(f"Error fetching unit: {e}")
                            finally:
                                if conn.is_connected():
                                    cursor.close()
                                    conn.close()
            
            except IndexError as ie:
                messagebox.showerror("Selection Error", 
                                    f"Unexpected data format in product selection.\n{str(ie)}")
            except Exception as e:
                messagebox.showerror("Error", 
                                   f"An error occurred while loading product details.\n{str(e)}")

    def add_product(self):
        # Get data from entry fields
        name = self.name_entry.get()
        category = self.category_entry.get()
        price = self.price_entry.get()
        stock = self.stock_entry.get()
        unit = self.unit_entry.get()
    
        # Validate inputs
        if not name or not category or not price or not stock:
            messagebox.showerror("Input Error", "All fields must be filled out.")
            return
    
        try:
            price = float(price)
            stock = float(stock)
        except ValueError:
            messagebox.showerror("Input Error", "Price and Stock Level must be numbers.")
            return
    
        # Convert stock level to base unit (grams or milliliters)
        try:
            stock_in_base_unit, base_unit = convert_to_base_unit(stock, unit)
        except ValueError as e:
            messagebox.showerror("Unit Error", str(e))
            return
    
        # Insert product into the database with base unit
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO products (name, category, price, stock_level, unit) VALUES (%s, %s, %s, %s, %s)",
                (name, category, price, stock_in_base_unit, base_unit)  # Store in base unit
            )
            conn.commit()
            messagebox.showinfo("Success", "Product added successfully!")
        except Error as e:
            messagebox.showerror("Database Error", f"Error adding product: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    
        # Clear entry fields and refresh product list
        self.clear_entries()
        self.populate_products()
    
    def update_product(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Selection Error", "Please select a product to update.")
            return
    
        # Get data from entry fields
        name = self.name_entry.get()
        category = self.category_entry.get()
        price = self.price_entry.get()
        stock = self.stock_entry.get()
        unit = self.unit_entry.get()
    
        # Validate inputs
        if not name or not category or not price or not stock:
            messagebox.showerror("Input Error", "All fields must be filled out.")
            return
    
        try:
            price = float(price)
            stock = float(stock)
        except ValueError:
            messagebox.showerror("Input Error", "Price and Stock Level must be numbers.")
            return
    
        # Convert stock level to base unit
        try:
            stock_in_base_unit, base_unit = convert_to_base_unit(stock, unit)
        except ValueError as e:
            messagebox.showerror("Unit Error", str(e))
            return
    
        # Update product in the database with base unit
        product_id = self.tree.item(selected_item, 'values')[0]
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            
            # First get the current base unit to ensure we're not changing unit types
            cursor.execute("SELECT unit FROM products WHERE id = %s", (product_id,))
            current_base_unit = cursor.fetchone()[0]
            
            if (current_base_unit in ['g', 'kg', 'lbs'] and base_unit != 'g') or \
               (current_base_unit in ['L', 'mL'] and base_unit != 'mL'):
                messagebox.showerror("Unit Error", 
                                   f"Cannot change unit type. Product uses {current_base_unit}")
                return
    
            cursor.execute(
                "UPDATE products SET name=%s, category=%s, price=%s, stock_level=%s, unit=%s WHERE id=%s",
                (name, category, price, stock_in_base_unit, base_unit, product_id)
            )
            conn.commit()
            messagebox.showinfo("Success", "Product updated successfully!")
        except Error as e:
            messagebox.showerror("Database Error", f"Error updating product: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    
        # Clear entry fields and refresh product list
        self.clear_entries()
        self.populate_products()

    def delete_product(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Selection Error", "Please select a product to delete.")
            return

        product_id = self.tree.item(selected_item, 'values')[0]

        # Confirm deletion
        if messagebox.askyesno("Confirm Deletion", "Are you sure you want to delete this product?"):
            conn = None
            try:
                conn = create_db_connection()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM products WHERE id=%s", (product_id,))
                conn.commit()
                messagebox.showinfo("Success", "Product deleted successfully!")
            except Error as e:
                messagebox.showerror("Database Error", f"Error deleting product: {e}")
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

            # Refresh product list
            self.populate_products()

    def clear_entries(self):
        self.name_entry.delete(0, tk.END)
        self.category_entry.delete(0, tk.END)
        self.price_entry.delete(0, tk.END)
        self.stock_entry.delete(0, tk.END)



# ----------------------------
# Inventory Management UI
# ----------------------------

class InventoryManagementUI:
    def __init__(self, parent):
        self.parent = parent
        self.create_widgets()
        self.populate_inventory()
    
    def create_widgets(self):
        # Configure grid layout - 2 columns (left for controls, right for treeview)
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=0)  # Fixed width for controls
        self.parent.grid_columnconfigure(1, weight=1)  # Expand treeview

        # Left Frame - Controls
        control_frame = tk.Frame(self.parent, padx=10, pady=10)
        control_frame.grid(row=0, column=0, sticky="nsew")

        # Right Frame - Inventory Treeview
        tree_frame = tk.Frame(self.parent)
        tree_frame.grid(row=0, column=1, sticky="nsew", padx=(0,10), pady=10)
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Stock Adjustment Section
        adjust_frame = tk.LabelFrame(control_frame, text="Stock Adjustment", padx=5, pady=5)
        adjust_frame.pack(fill="x", pady=5)

        tk.Label(adjust_frame, text="Product ID:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.product_id_entry = tk.Entry(adjust_frame, width=15)
        self.product_id_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')

        tk.Label(adjust_frame, text="Quantity:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.change_entry = tk.Entry(adjust_frame, width=15)
        self.change_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')

        tk.Label(adjust_frame, text="Unit:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.unit_entry = ttk.Combobox(adjust_frame, values=["kg", "g", "lbs", "L", "mL", "pcs", "m"], width=13)
        self.unit_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')

        # Buttons
        button_frame = tk.Frame(control_frame)
        button_frame.pack(fill="x", pady=10)

        button_style = {
            'width': 12,
            'font': ('Arial', 10, 'bold'),
            'borderwidth': 1,
            'relief': 'raised'
        }

        self.adjust_button = tk.Button(
            button_frame, text="Adjust Stock", 
            command=self.adjust_stock,
            bg="#007bff", fg="white", **button_style
        )
        self.adjust_button.pack(side=tk.LEFT, padx=5)

        self.refresh_button = tk.Button(
            button_frame, text="Refresh", 
            command=self.populate_inventory,
            bg="#6c757d", fg="white", **button_style
        )
        self.refresh_button.pack(side=tk.LEFT, padx=5)

        self.summary_button = tk.Button(
            button_frame, text="Sales Summary", 
            command=self.show_sales_summary,
            bg="#28a745", fg="white", **button_style
        )
        self.summary_button.pack(side=tk.LEFT, padx=5)

        # Configure button hover effects
        self.configure_button_hover()

        # Inventory Treeview
        tree_container = tk.LabelFrame(tree_frame, text="Inventory List", padx=5, pady=5)
        tree_container.pack(fill="both", expand=True)
        tree_container.grid_rowconfigure(0, weight=1)
        tree_container.grid_columnconfigure(0, weight=1)

        columns = ("ID", "Name", "Category", "Price", "Stock Level", "Unit")
        self.tree = ttk.Treeview(
            tree_container, 
            columns=columns, 
            show='headings',
            height=20,
            style="Custom.Treeview"
        )
        
        # Configure columns
        col_widths = [50, 150, 100, 80, 100, 50]
        for idx, col in enumerate(columns):
            self.tree.heading(col, text=col, anchor='w')
            self.tree.column(col, width=col_widths[idx], anchor='e' if col in ["Price"] else 'w')
        
        self.tree.grid(row=0, column=0, sticky="nsew")

        # Scrollbar
        scrollbar = ttk.Scrollbar(
            tree_container,
            orient=tk.VERTICAL,
            command=self.tree.yview
        )
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns')

        # Style configuration
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Custom.Treeview",
                      background="#2b2b2b",
                      foreground="white",
                      fieldbackground="#2b2b2b",
                      font=('Arial', 10),
                      borderwidth=0)
        style.configure("Custom.Treeview.Heading",
                      background="#3b3b3b",
                      foreground="white",
                      font=('Arial', 10, 'bold'),
                      borderwidth=0)
        style.map("Custom.Treeview",
                background=[('selected', '#0078D7')])

    def configure_button_hover(self):
        """Configure hover effects for buttons"""
        buttons = [
            (self.adjust_button, "#0069d9"),  # Darker blue
            (self.refresh_button, "#5a6268"), # Darker gray
            (self.summary_button, "#218838")  # Darker green
        ]
        
        for button, hover_color in buttons:
            button.bind("<Enter>", lambda e, b=button, c=hover_color: b.config(bg=c))
            button.bind("<Leave>", lambda e, b=button: b.config(bg=b.cget("bg")))
    
    def populate_inventory(self):
        # Clear the treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Fetch data from the database
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            
            # Ask user if they want to see low stock items
            show_low = messagebox.askyesno("View Options", "Show only low stock items?")
            
            if show_low:
                cursor.execute("SELECT * FROM low_stock_view")
                messagebox.showinfo("Info", "Showing low stock items (below 30% of average)")
            else:
                cursor.execute("SELECT id, name, category, price, stock_level, unit FROM products")
            
            rows = cursor.fetchall()

            # Insert data into the treeview
            for row in rows:
                if show_low:
                    # Using the view which already has converted units
                    id, name, stock_level, unit, category, price = row
                    self.tree.insert("", tk.END, values=(id, name, category, price, f"{stock_level:.2f} {unit}", unit))
                else:
                    # Original processing
                    id, name, category, price, stock_level, unit = row
                    displayed_stock, display_unit = convert_from_base_unit(stock_level, unit)
                    self.tree.insert("", tk.END, values=(id, name, category, price, f"{displayed_stock:.2f} {display_unit}", unit))
                    
        except Error as e:
            messagebox.showerror("Database Error", f"Error fetching inventory: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    
    def adjust_stock(self):
        product_id = self.product_id_entry.get().strip()
        quantity_change = self.change_entry.get().strip()
        unit = self.unit_entry.get().strip()
    
        if not product_id or not quantity_change or not unit:
            messagebox.showerror("Input Error", "All fields are required.")
            return
    
        try:
            product_id = int(product_id)
            quantity_change = float(quantity_change)
        except ValueError:
            messagebox.showerror("Input Error", "Product ID must be an integer and Change must be a number.")
            return
    
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
    
            # Check if product exists
            cursor.execute("SELECT stock_level, unit FROM products WHERE id = %s", (product_id,))
            result = cursor.fetchone()
            if not result:
                messagebox.showerror("Input Error", "Product not found.")
                return
    
            current_stock, current_unit = result
            current_stock = float(current_stock)  # Convert Decimal to float
    
            # Validate unit selection based on product type
            if current_unit in ["kg", "g"] and unit not in ["kg", "g"]:
                messagebox.showerror("Unit Error", "For weight products, please select either 'kg' or 'g'.")
                return
            elif current_unit in ["L", "mL"] and unit not in ["L", "mL"]:
                messagebox.showerror("Unit Error", "For liquid products, please select either 'L' or 'mL'.")
                return
            elif current_unit == "pcs" and unit != "pcs":
                messagebox.showerror("Unit Error", "For products measured in pieces, please select 'pcs'.")
                return
            elif current_unit == "m" and unit != "m":
                messagebox.showerror("Unit Error", "For products measured in meters, please select 'm'.")
                return
    
            # Check if the current stock is in base unit
            if current_unit == unit:
                new_stock = current_stock + quantity_change
            else:
                # Convert change to base unit
                change_in_base_unit, _ = convert_to_base_unit(quantity_change, unit)
                new_stock = current_stock + change_in_base_unit
    
            # Update the stock level in the database
            cursor.execute("UPDATE products SET stock_level = %s WHERE id = %s", (new_stock, product_id))
            
            # Record in stock history
            cursor.execute(
                "INSERT INTO stock_history (product_id, quantity_change, unit) VALUES (%s, %s, %s)",
                (product_id, quantity_change, unit)
            )
            
            conn.commit()
            messagebox.showinfo("Success", "Stock level updated successfully!")
            
            # Refresh the inventory display
            self.populate_inventory()
    
            # Clear input fields
            self.product_id_entry.delete(0, tk.END)
            self.change_entry.delete(0, tk.END)
            self.unit_entry.set('')
    
        except Error as e:
            messagebox.showerror("Database Error", f"Error adjusting stock: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()


    def show_sales_summary(self):
        # Create a new window
        summary_window = tk.Toplevel(self.parent)
        summary_window.title("Sales Summary")
        summary_window.geometry("800x400")
        
        # Create Treeview
        columns = ("Date", "Transactions", "Total Revenue", "Avg Sale", "Max Sale", "Min Sale")
        tree = ttk.Treeview(summary_window, columns=columns, show='headings')
        for col in columns:
            tree.heading(col, text=col)
            tree.column(col, width=120)
        tree.pack(expand=True, fill='both')
        
        # Add Scrollbar
        scrollbar = ttk.Scrollbar(summary_window, orient=tk.VERTICAL, command=tree.yview)
        tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Fetch and display data
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM daily_sales_summary ORDER BY sale_date DESC")
            
            for row in cursor.fetchall():
                tree.insert("", tk.END, values=(
                    row[0],  # date
                    row[1],  # transactions
                    f"{row[2]:.2f}",  # revenue
                    f"{row[3]:.2f}",  # avg sale
                    f"{row[4]:.2f}",  # max sale
                    f"{row[5]:.2f}"   # min sale
                ))
                
        except Error as e:
            messagebox.showerror("Database Error", f"Error fetching sales summary: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

# ----------------------------
# Sales Processing UI
# ----------------------------

class SalesProcessingUI:
    def __init__(self, parent):
        self.parent = parent
        self.create_widgets()
        self.populate_sales()
    
    def create_widgets(self):
        # Labels and Entry fields for sales processing
        tk.Label(self.parent, text="Product ID").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.product_id_entry = tk.Entry(self.parent)
        self.product_id_entry.grid(row=0, column=1, padx=10, pady=5)
        
        tk.Label(self.parent, text="Quantity Sold").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.quantity_entry = tk.Entry(self.parent)
        self.quantity_entry.grid(row=1, column=1, padx=10, pady=5)
        
        tk.Label(self.parent, text="Unit").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.unit_entry = ttk.Combobox(self.parent, values=["kg", "g", "lbs", "L", "mL", "pcs", "m"])
        self.unit_entry.grid(row=2, column=1, padx=10, pady=5)

        # Buttons
        tk.Button(self.parent, text="Process Sale", command=self.process_sale).grid(row=3, column=0, padx=10, pady=10)
        tk.Button(self.parent, text="Refresh", command=self.populate_sales).grid(row=3, column=1, padx=10, pady=10)
        
        # Sales List (Treeview)
        columns = ("ID", "Product ID", "Quantity", "Sale Price", "Total", "Date")
        self.tree = ttk.Treeview(self.parent, columns=columns, show='headings')
        for col in columns:
            self.tree.heading(col, text=col, anchor='w')
            if col == "Date":
                self.tree.column(col, width=150)
            else:
                self.tree.column(col, width=100)
        self.tree.grid(row=4, column=0, columnspan=2, padx=10, pady=10, sticky='nsew')
        
        # Configure grid weights for responsiveness
        self.parent.grid_rowconfigure(4, weight=1)
        self.parent.grid_columnconfigure(1, weight=1)
        
        # Scrollbar for the Treeview
        scrollbar = ttk.Scrollbar(self.parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=4, column=2, sticky='ns')
    
    def populate_sales(self):
        # Clear the treeview
        for item in self.tree.get_children():
            self.tree.delete(item)
        
        # Fetch data from the database using MySQL
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, product_id, quantity, sale_price, total_amount, date, unit FROM sales")
            rows = cursor.fetchall()

            # Insert data into the treeview
            for row in rows:
                # Combine quantity and unit for display
                quantity_with_unit = f"{row[2]} {row[6]}"  # row[2] is quantity, row[6] is unit
                self.tree.insert("", tk.END, values=(row[0], row[1], quantity_with_unit, row[3], row[4], row[5]))
        except Error as e:
            messagebox.showerror("Database Error", f"Failed to fetch sales data: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
    
    def process_sale(self):
        product_id = self.product_id_entry.get().strip()
        quantity = self.quantity_entry.get().strip()
        unit = self.unit_entry.get().strip()

        if not product_id or not quantity or not unit:
            messagebox.showerror("Input Error", "All fields are required.")
            return

        try:
            product_id = int(product_id)
            quantity = float(quantity)
        except ValueError:
            messagebox.showerror("Input Error", "Product ID must be an integer and Quantity must be a number.")
            return

        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()

            # Check if product exists
            cursor.execute("SELECT stock_level, unit, price FROM products WHERE id = %s", (product_id,))
            result = cursor.fetchone()
            if not result:
                messagebox.showerror("Error", "Product not found.")
                return

            current_stock, current_unit, product_price = result

            # Convert all values to float for consistent arithmetic
            current_stock = float(current_stock)
            product_price = float(product_price)
            quantity = float(quantity)

            # Validate unit selection based on product type
            if (current_unit in ["kg", "g"] and unit not in ["kg", "g"]) or \
               (current_unit in ["L", "mL"] and unit not in ["L", "mL"]) or \
               (current_unit == "pcs" and unit != "pcs") or \
               (current_unit == "m" and unit != "m"):
                messagebox.showerror("Unit Error", f"Invalid unit for this product. Please use {current_unit}.")
                return

            # Process the sale
            if current_unit == unit:
                new_stock = current_stock - quantity
            else:
                # Convert quantity to base unit
                quantity_in_base_unit, _ = convert_to_base_unit(quantity, unit)
                new_stock = current_stock - quantity_in_base_unit

            # Check if there is enough stock
            if new_stock < 0:
                messagebox.showerror("Stock Error", "Not enough stock available.")
                return

            # Calculate total price based on the unit
            if unit in ["g", "mL"]:  # If selling in smaller units
                total_price = (product_price / 1000) * quantity  # Convert price to per gram or per mL
            else:  # If selling in larger units (kg, L, pcs, m)
                total_price = product_price * quantity  # Calculate total price directly

            # Update the stock level in the database
            cursor.execute("UPDATE products SET stock_level = %s WHERE id = %s", (new_stock, product_id))

            # Insert the sale record into the sales table with total amount and unit
            cursor.execute("""
                INSERT INTO sales (product_id, quantity, sale_price, total_amount, unit) 
                VALUES (%s, %s, %s, %s, %s)
            """, (product_id, quantity, product_price, total_price, unit))

            conn.commit()  # Commit the transaction

            # Refresh the sales display
            self.populate_sales()

            # Clear input fields
            self.product_id_entry.delete(0, tk.END)
            self.quantity_entry.delete(0, tk.END)
            self.unit_entry.set('')

        except Error as e:
            if conn:
                conn.rollback()
            messagebox.showerror("Database Error", f"Failed to process sale: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def update_treeview(self):
        # Clear the treeview
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Fetch updated data from the database
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, product_id, CONCAT(quantity, ' ', unit) AS quantity, 
                       sale_price, total_amount, date 
                FROM sales
            """)
            rows = cursor.fetchall()

            # Insert updated data into the treeview
            for row in rows:
                self.tree.insert("", tk.END, values=row)
        except Error as e:
            messagebox.showerror("Database Error", f"Failed to update sales view: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()
# ----------------------------
# Billing Management UI
# ----------------------------


class BillingUI:
    def __init__(self, parent):
        self.parent = parent
        self.cart = []
        self.tax_rate = 5  # Example: 5% tax
        self.create_widgets()

    def create_widgets(self):
        # Configure grid layout - 2 columns (left for controls, right for cart)
        self.parent.grid_rowconfigure(0, weight=1)
        self.parent.grid_columnconfigure(0, weight=0)  # Don't expand left column
        self.parent.grid_columnconfigure(1, weight=1)  # Expand right column

        # Left Frame for controls
        left_frame = tk.Frame(self.parent, padx=10, pady=10)
        left_frame.grid(row=0, column=0, sticky="nsew")
        
        # Right Frame for cart Treeview
        right_frame = tk.Frame(self.parent)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(0,10), pady=10)
        right_frame.grid_rowconfigure(0, weight=1)
        right_frame.grid_columnconfigure(0, weight=1)

        # Product Search Section
        search_frame = tk.LabelFrame(left_frame, text="Product Search", padx=5, pady=5)
        search_frame.pack(fill="x", pady=5)
        
        tk.Label(search_frame, text="Search:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.search_entry = tk.Entry(search_frame, width=25)
        self.search_entry.grid(row=0, column=1, padx=5, pady=5, sticky='ew')
        self.search_entry.bind("<KeyRelease>", self.on_search)

        # Product Information Frame
        info_frame = tk.LabelFrame(left_frame, text="Product Information", padx=5, pady=5)
        info_frame.pack(fill="x", pady=5)
        
        tk.Label(info_frame, text="Name:").grid(row=0, column=0, padx=5, pady=2, sticky='w')
        self.product_name_label = tk.Label(info_frame, text="--", width=25, anchor='w')
        self.product_name_label.grid(row=0, column=1, padx=5, pady=2, sticky='w')
        
        tk.Label(info_frame, text="Stock:").grid(row=1, column=0, padx=5, pady=2, sticky='w')
        self.product_stock_label = tk.Label(info_frame, text="--", width=25, anchor='w')
        self.product_stock_label.grid(row=1, column=1, padx=5, pady=2, sticky='w')
        
        tk.Label(info_frame, text="Price:").grid(row=2, column=0, padx=5, pady=2, sticky='w')
        self.product_price_label = tk.Label(info_frame, text="--", width=25, anchor='w')
        self.product_price_label.grid(row=2, column=1, padx=5, pady=2, sticky='w')

        # Product ID and Quantity Frame
        input_frame = tk.LabelFrame(left_frame, text="Add to Cart", padx=5, pady=5)
        input_frame.pack(fill="x", pady=5)
        
        tk.Label(input_frame, text="Product ID:").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.product_id_entry = tk.Entry(input_frame, width=10)
        self.product_id_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        
        tk.Label(input_frame, text="Quantity:").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.quantity_entry = tk.Entry(input_frame, width=10)
        self.quantity_entry.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        tk.Label(input_frame, text="Unit:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.unit_entry = ttk.Combobox(input_frame, values=["kg", "g", "lbs", "L", "mL", "pcs", "m"], width=8)
        self.unit_entry.grid(row=2, column=1, padx=5, pady=5, sticky='w')

        # Buttons Frame
        button_frame = tk.Frame(left_frame)
        button_frame.pack(fill="x", pady=10)
        
        tk.Button(button_frame, text="Add to Cart", command=self.add_to_cart, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Remove", command=self.delete_from_cart, width=12).pack(side=tk.LEFT, padx=5)
        tk.Button(button_frame, text="Clear Cart", command=self.clear_cart, width=12).pack(side=tk.LEFT, padx=5)

        # Payment Frame
        payment_frame = tk.LabelFrame(left_frame, text="Payment Details", padx=5, pady=5)
        payment_frame.pack(fill="x", pady=5)
        
        tk.Label(payment_frame, text="Discount (%):").grid(row=0, column=0, padx=5, pady=5, sticky='w')
        self.discount_entry = tk.Entry(payment_frame, width=10)
        self.discount_entry.grid(row=0, column=1, padx=5, pady=5, sticky='w')
        
        tk.Label(payment_frame, text=f"Tax ({self.tax_rate}%):").grid(row=1, column=0, padx=5, pady=5, sticky='w')
        self.tax_label = tk.Label(payment_frame, text="0.00", width=10, anchor='e')
        self.tax_label.grid(row=1, column=1, padx=5, pady=5, sticky='w')
        
        tk.Label(payment_frame, text="Total:").grid(row=2, column=0, padx=5, pady=5, sticky='w')
        self.total_label = tk.Label(payment_frame, text="0.00", width=10, anchor='e')
        self.total_label.grid(row=2, column=1, padx=5, pady=5, sticky='w')
        
        tk.Label(payment_frame, text="Payment Method:").grid(row=3, column=0, padx=5, pady=5, sticky='w')
        self.payment_method = ttk.Combobox(payment_frame, values=["Cash", "Card", "Mobile Payment"], width=15)
        self.payment_method.grid(row=3, column=1, padx=5, pady=5, sticky='w')
        self.payment_method.current(0)  # Set default to "Cash"

        # Process Payment Button
        tk.Button(left_frame, text="Process Payment", command=self.process_payment, 
                 bg="#4CAF50", fg="white", font=('Arial', 10, 'bold')).pack(fill="x", pady=10)

        # Cart Treeview (Right Side)
        cart_frame = tk.LabelFrame(right_frame, text="Shopping Cart", padx=5, pady=5)
        cart_frame.pack(fill="both", expand=True)
        cart_frame.grid_rowconfigure(0, weight=1)
        cart_frame.grid_columnconfigure(0, weight=1)

        columns = ("Product ID", "Name", "Quantity", "Unit Price", "Total Price")
        self.cart_tree = ttk.Treeview(cart_frame, columns=columns, show='headings', height=20)
        
        # Configure columns
        col_widths = [80, 150, 80, 80, 80]
        for idx, col in enumerate(columns):
            self.cart_tree.heading(col, text=col)
            self.cart_tree.column(col, width=col_widths[idx], anchor='e' if col in ["Unit Price", "Total Price"] else 'w')
        
        self.cart_tree.grid(row=0, column=0, sticky="nsew")
        
        # Scrollbar for the Treeview
        scrollbar = ttk.Scrollbar(cart_frame, orient=tk.VERTICAL, command=self.cart_tree.yview)
        self.cart_tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=0, column=1, sticky='ns')

        # Style configuration
        style = ttk.Style()
        style.configure("Treeview.Heading", font=('Arial', 10, 'bold'))
        style.configure("Treeview", font=('Arial', 10), rowheight=25)
        style.configure("TCombobox", padding=5)

    def on_search(self, event):
        search_term = self.search_entry.get().strip()
        if not search_term:
            self.product_name_label.config(text="--")
            self.product_stock_label.config(text="--")
            self.product_price_label.config(text="--")
            self.product_id_entry.delete(0, tk.END)
            return
        
        conn = None
        cursor = None
        try:
            conn = create_db_connection()
            if conn is None:
                messagebox.showerror("Database Error", "Could not connect to database")
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT id, name, stock_level, price, unit FROM products WHERE name LIKE %s", ('%' + search_term + '%',))
            result = cursor.fetchone()  # Get only the first matching product
            
            # Consume any remaining results to avoid "unread result" error
            cursor.fetchall()
            
            if result:
                product_id, name, stock_level, price, unit = result
                self.product_id_entry.delete(0, tk.END)
                self.product_id_entry.insert(0, str(product_id))
                self.product_name_label.config(text=name)
                
                # Convert stock level for display
                if unit in ['g', 'kg']:
                    display_stock = stock_level / 1000 if unit == 'g' else stock_level
                    display_unit = 'kg'
                elif unit in ['mL', 'L']:
                    display_stock = stock_level / 1000 if unit == 'mL' else stock_level
                    display_unit = 'L'
                else:
                    display_stock = stock_level
                    display_unit = unit
                    
                self.product_stock_label.config(text=f"{display_stock:.2f} {display_unit}")
                self.product_price_label.config(text=f"{price:.2f}")
            else:
                self.product_id_entry.delete(0, tk.END)
                self.product_name_label.config(text="Not found")
                self.product_stock_label.config(text="--")
                self.product_price_label.config(text="--")
                
        except Error as e:
            messagebox.showerror("Database Error", f"Error searching for product: {e}")
        finally:
            # Close cursor and connection properly
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def add_to_cart(self):
        product_id = self.product_id_entry.get().strip()
        quantity = self.quantity_entry.get().strip()
        unit = self.unit_entry.get().strip()

        if not product_id or not quantity or not unit:
            messagebox.showerror("Input Error", "All fields are required.")
            return

        try:
            product_id = int(product_id)
            quantity = float(quantity)
        except ValueError:
            messagebox.showerror("Input Error", "Product ID must be an integer and Quantity must be a number.")
            return

        conn = None
        try:
            conn = create_db_connection()
            if conn is None:
                messagebox.showerror("Database Error", "Could not connect to database")
                return

            cursor = conn.cursor(buffered=True)
            cursor.execute("""
                SELECT name, price, stock_level, unit 
                FROM products 
                WHERE id = %s
            """, (product_id,))
            result = cursor.fetchone()

            if not result:
                messagebox.showerror("Error", "Product not found.")
                return

            name, price, stock_level, current_unit = result

            # Convert all numeric values to float explicitly
            price = float(price)
            stock_level = float(stock_level)
            quantity = float(quantity)

            # Validate unit
            if (current_unit in ["kg", "g"] and unit not in ["kg", "g"]) or \
               (current_unit in ["L", "mL"] and unit not in ["L", "mL"]) or \
               (current_unit == "pcs" and unit != "pcs") or \
               (current_unit == "m" and unit != "m"):
                messagebox.showerror("Unit Error", f"Invalid unit for this product. Please use {current_unit}.")
                return

            # Convert quantity to base units if needed
            if unit == "g" and current_unit == "kg":
                quantity_in_base = quantity / 1000
            elif unit == "mL" and current_unit == "L":
                quantity_in_base = quantity / 1000
            else:
                quantity_in_base = quantity

            # Check stock
            if quantity_in_base > stock_level:
                messagebox.showerror("Error", f"Insufficient stock. Available: {stock_level} {current_unit}")
                return

            # Calculate total price (using float arithmetic)
            if unit in ["g", "mL"]:
                total_price = (price / 1000) * quantity
            else:
                total_price = price * quantity

            # Add to cart
            self.cart.append({
                'product_id': product_id,
                'name': name,
                'quantity': f"{quantity} {unit}",
                'unit_price': price,
                'total_price': total_price
            })

            # Update Treeview
            self.cart_tree.insert("", tk.END, values=(
                product_id, 
                name, 
                f"{quantity} {unit}", 
                f"{price:.2f}", 
                f"{total_price:.2f}"
            ))

            self.update_totals()
            # Clear the input fields after adding to cart
            self.quantity_entry.delete(0, tk.END)
            self.unit_entry.set('')

        except Error as e:
            messagebox.showerror("Database Error", f"Error adding to cart: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()



    def delete_from_cart(self):
        selected_item = self.cart_tree.selection()
        if not selected_item:
            messagebox.showerror("Selection Error", "No item selected from the cart to delete.")
            return

        confirm = messagebox.askyesno("Confirm Delete", "Are you sure you want to delete this item from the cart?")
        if not confirm:
            return

        for item in selected_item:
            values = self.cart_tree.item(item, 'values')
            self.cart_tree.delete(item)
            for cart_item in self.cart:
                if cart_item['product_id'] == int(values[0]):
                    self.cart.remove(cart_item)
                    break

        self.update_totals()

    def update_totals(self):
        subtotal = sum(item['total_price'] for item in self.cart)
        discount = 0
        discount_input = self.discount_entry.get().strip()
        if discount_input:
            try:
                discount = (float(discount_input) / 100) * subtotal
            except ValueError:
                messagebox.showerror("Input Error", "Discount must be a number.")
                return

        tax = (self.tax_rate / 100) * (subtotal - discount)
        total = (subtotal - discount) + tax
        self.tax_label.config(text=f"{tax:.2f}")
        self.total_label.config(text=f"{total:.2f}")

    def process_payment(self):
        if not self.cart:
            messagebox.showerror("Cart Error", "Cart is empty.")
            return

        discount_input = self.discount_entry.get().strip()
        discount = 0
        if discount_input:
            try:
                discount = float(discount_input)
            except ValueError:
                messagebox.showerror("Input Error", "Discount must be a number.")
                return

        subtotal = 0  # Initialize subtotal
        for item in self.cart:
            # Calculate the total price based on the quantity and unit price
            quantity_str = item['quantity']
            quantity_value = float(quantity_str.split()[0])  # Extract the numeric part
            unit = quantity_str.split()[1]  # Extract the unit

            # Determine the price based on the unit
            if unit in ["g", "mL"]:  # If selling in smaller units
                # Convert the unit price to the price per gram or milliliter
                base_quantity, _ = convert_to_base_unit(1, "kg" if unit == "g" else "L")  # Get base quantity for conversion
                price_per_unit = item['unit_price'] / base_quantity  # Calculate price per gram or milliliter
                total_price = price_per_unit * quantity_value  # Calculate total price for the quantity sold
            else:  # If selling in larger units (kg, L, pcs, m)
                total_price = item['unit_price'] * quantity_value  # Calculate total price directly

            subtotal += total_price  # Add to subtotal

        discount_amount = (discount / 100) * subtotal if discount else 0
        tax = (self.tax_rate / 100) * (subtotal - discount_amount)
        total = (subtotal - discount_amount) + tax

        payment_method = self.payment_method.get()

        confirm = messagebox.askyesno("Confirm Payment", 
                                     f"Total Amount: {total:.2f}\nPayment Method: {payment_method}\nDo you want to proceed?")
        if not confirm:
            return

        conn = None
        cursor = None
        try:
            conn = create_db_connection()
            if conn is None:
                messagebox.showerror("Database Error", "Could not connect to database")
                return

            cursor = conn.cursor()

            # Start transaction
            cursor.execute("START TRANSACTION")

            # Process each item in the cart as part of the transaction
            for item in self.cart:
                product_id = item['product_id']
                quantity = item['quantity'].split()[0]  # Extract quantity from the string
                unit = item['quantity'].split()[1]  # Extract unit from the string
                quantity_in_base_unit, _ = convert_to_base_unit(float(quantity), unit)  # Convert to base unit

                # Check current stock level (within transaction)
                cursor.execute("SELECT stock_level, unit FROM products WHERE id = %s FOR UPDATE", (product_id,))
                result = cursor.fetchone()
                if not result:
                    raise Error(f"Product with ID {product_id} not found")

                current_stock, current_unit = result
                current_stock = float(current_stock)

                # Validate stock availability
                if quantity_in_base_unit > current_stock:
                    raise Error(f"Insufficient stock for product ID {product_id}. Available: {current_stock} {current_unit}")

                # Update stock level in the products table
                cursor.execute("UPDATE products SET stock_level = stock_level - %s WHERE id = %s", 
                             (quantity_in_base_unit, product_id))

                # Insert into sales table
                cursor.execute("""
                    INSERT INTO sales 
                    (product_id, quantity, sale_price, total_amount, unit) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (product_id, quantity, item['unit_price'], total_price, unit))

                # Record in stock history
                cursor.execute(
                    "INSERT INTO stock_history (product_id, quantity_change, unit) VALUES (%s, %s, %s)",
                    (product_id, -float(quantity), unit)  # Negative quantity for sales
                )

            # If all operations succeeded, commit the transaction
            conn.commit()

            # Generate receipt
            receipt = Receipt(self.cart, subtotal, discount_amount, tax, total, payment_method)
            receipt.generate_receipt()

            messagebox.showinfo("Success", "Payment processed and receipt generated.")

            # Clear cart and UI
            self.cart = []
            for item in self.cart_tree.get_children():
                self.cart_tree.delete(item)
            self.update_totals()
            self.discount_entry.delete(0, tk.END)

        except Error as e:
            if conn:
                conn.rollback()
            messagebox.showerror("Transaction Error", 
                               f"Error processing payment. All changes have been rolled back.\nError: {e}")
        except Exception as e:
            if conn:
                conn.rollback()
            messagebox.showerror("System Error", 
                               f"Unexpected error. All changes have been rolled back.\nError: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def clear_cart(self):
        self.cart = []
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        self.update_totals()
        self.discount_entry.delete(0, tk.END)


# ----------------------------
# Receipt Generation
# ----------------------------

class Receipt:
    def __init__(self, cart, subtotal, discount, tax, total, payment_method):
        self.cart = cart
        self.subtotal = subtotal
        self.discount = discount
        self.tax = tax
        self.total = total
        self.payment_method = payment_method
        self.filename = f"receipt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"

    def generate_receipt(self):
        c = canvas.Canvas(self.filename, pagesize=letter)
        width, height = letter

        # Header
        c.setFont("Helvetica-Bold", 20)
        c.drawString(200, 750, "UET Cash & Carry")

        # Date and Time
        c.setFont("Helvetica", 10)
        c.drawString(50, 730, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        # Table Headers
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, 700, "Product ID")
        c.drawString(130, 700, "Name")
        c.drawString(300, 700, "Quantity")
        c.drawString(380, 700, "Unit Price")
        c.drawString(480, 700, "Total Price")

        # Draw a line
        c.line(50, 695, 550, 695)

        # Table Content
        y = 680
        c.setFont("Helvetica", 12)
        for item in self.cart:
            c.drawString(50, y, str(item['product_id']))
            c.drawString(130, y, item['name'])
            c.drawString(300, y, str(item['quantity']))
            c.drawString(380, y, f"{item['unit_price']:.2f}")
            c.drawString(480, y, f"{item['total_price']:.2f}")
            y -= 20
            if y < 100:
                c.showPage()
                y = 750

        # Totals
        y -= 10
        c.setFont("Helvetica-Bold", 12)
        c.drawString(300, y, "Subtotal:")
        c.drawString(480, y, f"{self.subtotal:.2f}")
        y -= 20
        c.drawString(300, y, "Discount:")
        c.drawString(480, y, f"{self.discount:.2f}")
        y -= 20
        c.drawString(300, y, f"Tax ({5}%):")
        c.drawString(480, y, f"{self.tax:.2f}")
        y -= 20
        c.drawString(300, y, "Total:")
        c.drawString(480, y, f"{self.total:.2f}")
        y -= 20
        c.drawString(300, y, "Payment Method:")
        c.drawString(480, y, self.payment_method)

        # Footer
        y -= 40
        c.setFont("Helvetica-Oblique", 10)
        c.drawString(200, y, "Thank you for shopping with us!")

        c.save()







# ======================
# DEMAND FORECASTING MODULE
# ======================

import matplotlib
matplotlib.use('Agg')  # Set before importing pyplot
from matplotlib import pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from collections import defaultdict
from datetime import datetime
import traceback

class DemandForecaster:
    def __init__(self):
        self.seasonal_factors = {
            'winter': 1.2,  # Dec-Feb
            'spring': 1.0,  # Mar-May
            'summer': 1.3,  # Jun-Aug
            'fall': 1.1     # Sep-Nov
        }
        self.holiday_boost = {
            'New Year': 1.5,
            'Eid': 1.8,
            'Independence Day': 1.3,
            'Christmas': 1.6
        }

    def get_season(self, date):
        month = date.month
        if 3 <= month <= 5:
            return 'spring'
        elif 6 <= month <= 8:
            return 'summer'
        elif 9 <= month <= 11:
            return 'fall'
        return 'winter'

    def get_holiday(self, date):
        holidays = {
            (1, 1): 'New Year',
            (7, 14): 'Independence Day',
            (12, 25): 'Christmas'
        }
        return holidays.get((date.month, date.day))

    def classify_demand(self, quantity):
        """Convert sales quantity to demand level"""
        if quantity < 10: return 'low'
        elif 10 <= quantity < 30: return 'medium'
        return 'high'

    def train(self, product_id):
        """Train model using historical sales data"""
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            
            # Get 1 year of sales data
            cursor.execute("""
                SELECT DATE(date), SUM(quantity)
                FROM sales 
                WHERE product_id = %s 
                  AND date >= DATE_SUB(CURDATE(), INTERVAL 1 YEAR)
                GROUP BY DATE(date)
                ORDER BY date
            """, (product_id,))
            rows = cursor.fetchall()

            if not rows:
                print(f"No sales data for product {product_id}")
                return False

            # Calculate priors (baseline probabilities)
            demand_counts = defaultdict(int)
            for _, qty in rows:
                demand_counts[self.classify_demand(float(qty))] += 1
            
            total_days = len(rows)
            self.priors = {
                'low': demand_counts['low'] / total_days,
                'medium': demand_counts['medium'] / total_days,
                'high': demand_counts['high'] / total_days
            }

            # Calculate likelihoods (conditional probabilities)
            self.likelihoods = {
                'season': defaultdict(lambda: defaultdict(int)),
                'holiday': defaultdict(lambda: defaultdict(int)),
                'day_of_week': defaultdict(lambda: defaultdict(int))
            }

            for date_str, qty in rows:
                date = datetime.strptime(str(date_str), '%Y-%m-%d')
                demand = self.classify_demand(float(qty))
                
                # Season factor
                season = self.get_season(date)
                self.likelihoods['season'][season][demand] += 1
                
                # Holiday factor
                if holiday := self.get_holiday(date):
                    self.likelihoods['holiday'][holiday][demand] += 1
                
                # Day of week factor
                day = date.strftime('%A')
                self.likelihoods['day_of_week'][day][demand] += 1

            # Normalize probabilities
            for factor in self.likelihoods:
                for value in self.likelihoods[factor]:
                    total = sum(self.likelihoods[factor][value].values())
                    for level in self.likelihoods[factor][value]:
                        self.likelihoods[factor][value][level] /= total

            return True

        except Exception as e:
            print(f"Training error: {traceback.format_exc()}")
            return False
        finally:
            if conn and conn.is_connected():
                conn.close()

    def predict(self, date):
        """Predict demand for a future date"""
        if not hasattr(self, 'priors'):
            raise ValueError("Model not trained")

        # Prepare features
        features = {
            'season': self.get_season(date),
            'holiday': self.get_holiday(date),
            'day_of_week': date.strftime('%A')
        }

        # Calculate posterior probabilities
        posteriors = {}
        for level in ['low', 'medium', 'high']:
            posterior = self.priors[level]
            
            # Multiply by all feature likelihoods
            for factor, value in features.items():
                if value:  # Only if feature exists (e.g., not all dates are holidays)
                    posterior *= self.likelihoods[factor][value].get(level, 0.001)  # Smoothing
            
            posteriors[level] = posterior

        # Normalize and return best prediction
        total = sum(posteriors.values())
        return max(posteriors.items(), key=lambda x: x[1]/total)[0]

class DemandForecastingUI:
    def __init__(self, parent):
        self.parent = parent
        self.forecaster = DemandForecaster()
        self.setup_ui()

    def setup_ui(self):
        # Main container
        self.frame = tk.Frame(self.parent, padx=20, pady=20)
        self.frame.pack(fill=tk.BOTH, expand=True)

        # Product Selection
        tk.Label(self.frame, text="Product:", font=('Arial', 12)).grid(row=0, column=0, sticky='w')
        self.product_combo = ttk.Combobox(self.frame, font=('Arial', 12), width=25)
        self.product_combo.grid(row=0, column=1, padx=10, pady=5)
        self.load_products()

        # Date Selection
        tk.Label(self.frame, text="Forecast Date:", font=('Arial', 12)).grid(row=1, column=0, sticky='w')
        self.date_entry = DateEntry(self.frame, font=('Arial', 12), width=15, 
                                  date_pattern='yyyy-mm-dd')
        self.date_entry.grid(row=1, column=1, sticky='w', padx=10, pady=5)

        # Buttons
        btn_frame = tk.Frame(self.frame)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=10)
        
        tk.Button(btn_frame, text="Train Model", command=self.train_model,
                 bg="#4CAF50", fg="white", font=('Arial', 12)).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Predict", command=self.predict_demand,
                 bg="#2196F3", fg="white", font=('Arial', 12)).pack(side=tk.LEFT, padx=5)

        # Results Display
        self.result_var = tk.StringVar()
        tk.Label(self.frame, textvariable=self.result_var, font=('Arial', 14, 'bold'),
                fg="#333").grid(row=3, column=0, columnspan=2, pady=10)

        # Visualization
        self.viz_frame = tk.Frame(self.frame, bg='white', bd=2, relief=tk.SUNKEN)
        self.viz_frame.grid(row=4, column=0, columnspan=2, sticky='nsew', pady=10)
        
        # Configure grid weights
        self.frame.grid_rowconfigure(4, weight=1)
        self.frame.grid_columnconfigure(1, weight=1)

    def load_products(self):
        """Populate product dropdown"""
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM products ORDER BY name")
            self.product_combo['values'] = [f"{pid} - {name}" for pid, name in cursor.fetchall()]
            if self.product_combo['values']:
                self.product_combo.current(0)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load products:\n{str(e)}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def train_model(self):
        """Train the forecasting model"""
        try:
            pid = int(self.product_combo.get().split(' - ')[0])
            if self.forecaster.train(pid):
                messagebox.showinfo("Success", "Model trained successfully!")
            else:
                messagebox.showerror("Error", "Insufficient sales data for training")
        except Exception as e:
            messagebox.showerror("Error", f"Training failed:\n{str(e)}")

    def predict_demand(self):
        """Make and display prediction"""
        try:
            # Validate
            if not hasattr(self.forecaster, 'priors'):
                raise ValueError("Train the model first")
            
            pid = int(self.product_combo.get().split(' - ')[0])
            date = self.date_entry.get_date()
            
            # Predict
            prediction = self.forecaster.predict(date)
            self.result_var.set(f"Predicted Demand: {prediction.upper()}")
            
            # Visualize
            self.show_history(pid, date, prediction)
            
        except Exception as e:
            messagebox.showerror("Error", f"Prediction failed:\n{str(e)}")

    def show_history(self, product_id, pred_date, prediction):
        """Display historical sales graph"""
        for widget in self.viz_frame.winfo_children():
            widget.destroy()
            
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DATE(date), SUM(quantity)
                FROM sales 
                WHERE product_id = %s
                GROUP BY DATE(date)
                ORDER BY date
            """, (product_id,))
            dates, quantities = zip(*cursor.fetchall())
            
            # Create plot
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.plot(dates, quantities, 'b-', label='Historical Sales')
            ax.axvline(x=pred_date, color='r', linestyle='--', 
                      label=f'Prediction: {prediction}')
            
            # Formatting
            ax.set_title(f"Sales History for Product {product_id}")
            ax.set_xlabel("Date")
            ax.set_ylabel("Units Sold")
            ax.legend()
            ax.grid(True)
            fig.autofmt_xdate()
            
            # Embed
            canvas = FigureCanvasTkAgg(fig, self.viz_frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            
            # Add toolbar
            toolbar = NavigationToolbar2Tk(canvas, self.viz_frame)
            toolbar.update()
            
        except Exception as e:
            tk.Label(self.viz_frame, text=f"Graph unavailable: {str(e)}", 
                    fg="red").pack()
        finally:
            if conn and conn.is_connected():
                conn.close()











# ----------------------------
# Sales Report UI
# ----------------------------

class SalesReportUI:
    def __init__(self, parent):
        self.parent = parent
        self.create_widgets()

    def create_widgets(self):
        # Report Type Selection
        tk.Label(self.parent, text="Report Type").grid(row=0, column=0, padx=10, pady=10, sticky='w')
        self.report_type = tk.StringVar()
        self.report_type.set("Daily")
        report_options = ["Daily", "Weekly", "Monthly"]
        self.report_menu = ttk.Combobox(self.parent, textvariable=self.report_type, values=report_options, state="readonly")
        self.report_menu.grid(row=0, column=1, padx=10, pady=10, sticky='w')

        # Date Range Selection
        tk.Label(self.parent, text="Start Date (YYYY-MM-DD)").grid(row=1, column=0, padx=10, pady=10, sticky='w')
        self.start_date_entry = tk.Entry(self.parent)
        self.start_date_entry.grid(row=1, column=1, padx=10, pady=10, sticky='w')

        tk.Label(self.parent, text="End Date (YYYY-MM-DD)").grid(row=2, column=0, padx=10, pady=10, sticky='w')
        self.end_date_entry = tk.Entry(self.parent)
        self.end_date_entry.grid(row=2, column=1, padx=10, pady=10, sticky='w')

        # Buttons
        tk.Button(self.parent, text="Generate Report", command=self.generate_report).grid(row=3, column=0, padx=10, pady=10)
        tk.Button(self.parent, text="Export to CSV", command=self.export_csv).grid(row=3, column=1, padx=10, pady=10)
        tk.Button(self.parent, text="Export to Excel", command=self.export_excel).grid(row=3, column=2, padx=10, pady=10)

        # Report Display (Treeview)
        columns = ("Sale ID", "Product ID", "Quantity", "Sale Price", "Total", "Date")
        self.tree = ttk.Treeview(self.parent, columns=columns, show='headings')
        for col in columns:
            self.tree.heading(col, text=col, anchor='w')
            if col == "Product Name":
                self.tree.column(col, width=200)
            elif col == "Date":
                self.tree.column(col, width=150)
            else:
                self.tree.column(col, width=100)
        self.tree.grid(row=4, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')

        # Configure grid weights for responsiveness
        self.parent.grid_rowconfigure(4, weight=1)
        self.parent.grid_columnconfigure(2, weight=1)

        # Scrollbar for the Treeview
        scrollbar = ttk.Scrollbar(self.parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=4, column=3, sticky='ns')

    def generate_report(self):
        report_type = self.report_type.get()
        start_date = self.start_date_entry.get().strip()
        end_date = self.end_date_entry.get().strip()

        if not start_date or not end_date:
            messagebox.showerror("Input Error", "Please enter both start and end dates.")
            return

        # Validate date format
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            datetime.strptime(end_date, "%Y-%m-%d")
        except ValueError:
            messagebox.showerror("Input Error", "Dates must be in YYYY-MM-DD format.")
            return

        # Fetch sales data based on the report type
        conn = None
        cursor = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()

            # Updated SQL query to fetch total_amount directly from the sales table
            query = """
                SELECT sales.id, sales.product_id, products.name, sales.quantity, 
                       sales.sale_price, sales.total_amount, sales.date, sales.unit 
                FROM sales 
                JOIN products ON sales.product_id = products.id 
                WHERE sales.date BETWEEN %s AND %s 
                ORDER BY sales.date
            """
            cursor.execute(query, (start_date, end_date))
            rows = cursor.fetchall()

            # Clear the treeview before inserting new data
            for row in self.tree.get_children():
                self.tree.delete(row)

            # Insert fetched data into the treeview
            for row in rows:
                # Combine quantity and unit for display
                quantity_with_unit = f"{row[3]} {row[7]}"  # row[3] is quantity, row[7] is unit
                self.tree.insert("", "end", values=(row[0], row[1], quantity_with_unit, row[4], row[5], row[6]))

        except Error as e:
            messagebox.showerror("Database Error", f"Error generating report: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".csv",
                                                 filetypes=[("CSV files", ".csv"), ("All files", ".*")])
        if not file_path:
            return

        with open(file_path, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            # Write headers
            headers = self.tree["columns"]
            writer.writerow(headers)
            # Write data
            for row in self.tree.get_children():
                writer.writerow(self.tree.item(row)["values"])

        messagebox.showinfo("Export Successful", f"Report exported to {file_path}")

    def export_excel(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".xlsx",
                                                 filetypes=[("Excel files", ".xlsx"), ("All files", ".*")])
        if not file_path:
            return

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Sales Report"

        # Write headers
        headers = self.tree["columns"]
        sheet.append(headers)

        # Write data
        for row in self.tree.get_children():
            sheet.append(self.tree.item(row)["values"])

        workbook.save(file_path)
        messagebox.showinfo("Export Successful", f"Report exported to {file_path}")



# ----------------------------
# Enhanced Sales Report UI
# ----------------------------

class EnhancedSalesReportUI:
    def __init__(self, parent):
        self.parent = parent
        self.create_widgets()
        self.load_report()

    def create_widgets(self):
        # Configure main frame
        self.parent.grid_rowconfigure(1, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)
        
        # Filter controls frame
        filter_frame = tk.Frame(self.parent, bg="#f0f0f0", padx=10, pady=10)
        filter_frame.grid(row=0, column=0, sticky="ew")
        
        # Date From filter
        tk.Label(filter_frame, text="From:", bg="#f0f0f0").grid(row=0, column=0, padx=5, sticky='e')
        self.from_date = DateEntry(filter_frame, 
                                 width=12, 
                                 background='darkblue',
                                 foreground='white',
                                 date_pattern='yyyy-mm-dd')
        self.from_date.grid(row=0, column=1, padx=5, sticky='w')
        self.from_date.set_date(datetime.now() - timedelta(days=30))  # Default to 30 days ago
        
        # Date To filter
        tk.Label(filter_frame, text="To:", bg="#f0f0f0").grid(row=0, column=2, padx=5, sticky='e')
        self.to_date = DateEntry(filter_frame, 
                               width=12, 
                               background='darkblue',
                               foreground='white',
                               date_pattern='yyyy-mm-dd')
        self.to_date.grid(row=0, column=3, padx=5, sticky='w')
        self.to_date.set_date(datetime.now())  # Default to today
        
        # Buttons
        button_frame = tk.Frame(filter_frame, bg="#f0f0f0")
        button_frame.grid(row=0, column=4, columnspan=3, padx=10)
        
        tk.Button(button_frame, text="🔍 Generate", command=self.load_report,
                bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="📤 Export CSV", command=self.export_csv,
                bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2)

        # Treeview
        columns = [
            "ID", "Product", "Quantity", "Unit", "Unit Price", 
            "Total", "Date", "Daily Total", "Running Total", "Rank"
        ]
        self.tree = ttk.Treeview(self.parent, columns=columns, show='headings', height=20)
        
        # Configure columns
        col_widths = [50, 120, 70, 50, 80, 80, 100, 90, 90, 50]
        for idx, col in enumerate(columns):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths[idx], anchor='e' if col in ["Unit Price", "Total", "Daily Total", "Running Total"] else 'w')
        
        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky='ns')

    def load_report(self):
        # Clear existing data
        for row in self.tree.get_children():
            self.tree.delete(row)
            
        # Get date range
        date_from = self.from_date.get_date()
        date_to = self.to_date.get_date()
        
        # Build query
        query = """
            SELECT * FROM enhanced_sales_report
            WHERE date BETWEEN %s AND %s
            ORDER BY date DESC, daily_rank
        """
        params = [date_from, date_to + timedelta(days=1)]  # +1 day to include entire end day
        
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            # Insert data with proper formatting
            for row in cursor.fetchall():
                self.tree.insert("", "end", values=(
                    row[0],  # ID
                    row[1],  # Product
                    f"{row[2]:.2f}",  # Quantity
                    row[3],  # Unit
                    f"{row[4]:.2f}",  # Unit Price
                    f"{row[5]:.2f}",  # Total
                    row[6].strftime("%Y-%m-%d %H:%M"),  # Date
                    f"{row[7]:.2f}",  # Daily Total
                    f"{row[8]:.2f}",  # Running Total
                    row[9]   # Rank
                ))
                
        except Error as e:
            messagebox.showerror("Database Error", f"Failed to load report:\n{str(e)}")
        finally:
            if conn and conn.is_connected():
                conn.close()

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"sales_report_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                
                # Write headers
                headers = [self.tree.heading(col)['text'] for col in self.tree['columns']]
                writer.writerow(headers)
                
                # Write data
                for row_id in self.tree.get_children():
                    row_data = self.tree.item(row_id)['values']
                    # Remove $ symbols for clean CSV data
                    row_data = [x.replace('$', '') if isinstance(x, str) and '$' in x else x for x in row_data]
                    writer.writerow(row_data)
                    
            messagebox.showinfo("Export Complete", f"Report saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export:\n{str(e)}")





class OLAPManager:
    def __init__(self):
        self.conn = create_db_connection()

    def refresh_cube(self):
        """Updates all OLAP data"""
        try:
            cursor = self.conn.cursor()
            cursor.callproc("refresh_sales_cube")
            self.conn.commit()
            messagebox.showinfo("Success", "OLAP cube refreshed successfully!")
        except Error as e:
            messagebox.showerror("Error", f"Failed to refresh cube: {e}")
        finally:
            if self.conn.is_connected():
                cursor.close()

    def get_category_trends(self, days=30):
        """Returns sales by category for time period"""
        try:
            cursor = self.conn.cursor()
            cursor.execute('''
                SELECT category, sale_date, SUM(total_sales)
                FROM sales_cube
                WHERE sale_date >= DATE_SUB(CURDATE(), INTERVAL %s DAY)
                GROUP BY category, sale_date
                ORDER BY sale_date
            ''', (days,))
            return cursor.fetchall()
        except Error as e:
            messagebox.showerror("Error", f"Failed to get trends: {e}")
            return []
        finally:
            if self.conn.is_connected():
                cursor.close()



# ----------------------------
# OLAP Analysis UI
# ----------------------------

class OLAPAnalysisUI:
    def __init__(self, parent):
        self.parent = parent
        self.olap = OLAPManager()
        self.create_widgets()
        
    def create_widgets(self):
        # Configure main frame
        self.parent.grid_rowconfigure(1, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)
        
        # Filter controls frame
        filter_frame = tk.Frame(self.parent, bg="#f0f0f0", padx=10, pady=10)
        filter_frame.grid(row=0, column=0, sticky="ew")
        
        # Group By selection
        tk.Label(filter_frame, text="Group By:", bg="#f0f0f0").grid(row=0, column=0, padx=5, sticky='e')
        self.group_by = ttk.Combobox(filter_frame, values=["Category", "Product", "Day"], state="readonly")
        self.group_by.grid(row=0, column=1, padx=5, sticky='w')
        self.group_by.set("Category")
        
        # Date range selection
        tk.Label(filter_frame, text="From:", bg="#f0f0f0").grid(row=0, column=2, padx=5, sticky='e')
        self.start_date = DateEntry(filter_frame, width=12, background='darkblue', foreground='white', date_pattern='yyyy-mm-dd')
        self.start_date.grid(row=0, column=3, padx=5, sticky='w')
        self.start_date.set_date(datetime.now() - timedelta(days=7))
        
        tk.Label(filter_frame, text="To:", bg="#f0f0f0").grid(row=0, column=4, padx=5, sticky='e')
        self.end_date = DateEntry(filter_frame, width=12, background='darkblue', foreground='white', date_pattern='yyyy-mm-dd')
        self.end_date.grid(row=0, column=5, padx=5, sticky='w')
        self.end_date.set_date(datetime.now())
        
        # Buttons
        button_frame = tk.Frame(filter_frame, bg="#f0f0f0")
        button_frame.grid(row=0, column=6, columnspan=2, padx=10)
        
        tk.Button(button_frame, text="Analyze", command=self.generate_report,
                bg="#4CAF50", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="Refresh Data", command=self.refresh_data,
                bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="Export CSV", command=self.export_csv,
                bg="#9C27B0", fg="white").pack(side=tk.LEFT, padx=2)
        
        # Results Treeview
        columns = ["Group", "Total Sales", "Quantity Sold", "Transactions", "Avg Sale"]
        self.tree = ttk.Treeview(self.parent, columns=columns, show='headings', height=20)
        
        # Configure columns
        col_widths = [200, 120, 120, 120, 120]
        col_anchors = ['w', 'e', 'e', 'e', 'e']
        
        for idx, col in enumerate(columns):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths[idx], anchor=col_anchors[idx])
        
        self.tree.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky='ns')
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = tk.Label(self.parent, textvariable=self.status_var, bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.status_var.set("Ready")
        
    def refresh_data(self):
        try:
            self.status_var.set("Refreshing OLAP data...")
            self.parent.update()
            
            self.olap.refresh_cube()
            self.status_var.set("OLAP data refreshed successfully!")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to refresh OLAP data:\n{str(e)}")
            self.status_var.set("Error refreshing data")
            
    def generate_report(self):
        try:
            self.status_var.set("Generating report...")
            self.parent.update()
            
            # Clear existing data
            for row in self.tree.get_children():
                self.tree.delete(row)
                
            # Get parameters
            group_by = self.group_by.get().lower()
            start_date = self.start_date.get_date()
            end_date = self.end_date.get_date()
            
            # Get data from OLAP manager
            results = self.olap.get_sales_report(
                group_by=group_by,
                start_date=start_date,
                end_date=end_date
            )
            
            # Insert data into treeview
            for row in results:
                self.tree.insert("", "end", values=(
                    row[0],  # Group
                    f"Rs{row[1]:,.2f}",  # Total Sales
                    f"{row[2]:,.2f}",    # Quantity
                    row[3],              # Transactions
                    f"Rs{row[4]:,.2f}"   # Avg Sale
                ))
                
            self.status_var.set(f"Report generated: {len(results)} records")
            
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate report:\n{str(e)}")
            self.status_var.set("Error generating report")
            
    def export_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv")],
            initialfile=f"olap_report_{datetime.now().strftime('%Y%m%d')}.csv"
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                
                # Write headers
                headers = [self.tree.heading(col)['text'] for col in self.tree['columns']]
                writer.writerow(headers)
                
                # Write data
                for row_id in self.tree.get_children():
                    row_data = self.tree.item(row_id)['values']
                    # Remove Rs symbols for clean CSV data
                    row_data = [x.replace('Rs', '') if isinstance(x, str) and 'Rs' in x else x for x in row_data]
                    writer.writerow(row_data)
                    
            messagebox.showinfo("Export Complete", f"Report saved to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export:\n{str(e)}")
        
        
# ----------------------------
# OLAP Manager
# ----------------------------


# CREATE TABLE IF NOT EXISTS sales_cube (
#                     id INT AUTO_INCREMENT PRIMARY KEY,
#                     product_id INT,
#                     product_name VARCHAR(255),
#                     category VARCHAR(255),
#                     sale_date DATE,
#                     sale_year INT,
#                     sale_month INT,
#                     sale_quarter INT,
#                     sale_week INT,
#                     total_sales DECIMAL(12,2),
#                     total_quantity DECIMAL(10,2),
#                     transaction_count INT,
#                     avg_sale DECIMAL(10,2),
#                     INDEX (product_id),
#                     INDEX (category),
#                     INDEX (sale_date),
#                     INDEX (sale_year),
#                     INDEX (sale_month),
#                     INDEX (sale_quarter)
#                 )
                
                
# TRUNCATE TABLE sales_cube

# INSERT INTO sales_cube (
#                     product_id, product_name, category, 
#                     sale_date, sale_year, sale_month, sale_quarter, sale_week,
#                     total_sales, total_quantity, transaction_count, avg_sale
#                 )
#                 SELECT 
#                     s.product_id,
#                     p.name AS product_name,
#                     p.category,
#                     DATE(s.date) AS sale_date,
#                     YEAR(s.date) AS sale_year,
#                     MONTH(s.date) AS sale_month,
#                     QUARTER(s.date) AS sale_quarter,
#                     WEEK(s.date) AS sale_week,
#                     SUM(s.total_amount) AS total_sales,
#                     SUM(s.quantity) AS total_quantity,
#                     COUNT(DISTINCT s.id) AS transaction_count,
#                     AVG(s.total_amount) AS avg_sale
#                 FROM sales s
#                 JOIN products p ON s.product_id = p.id
#                 GROUP BY 
#                     s.product_id, p.name, p.category, 
#                     DATE(s.date), YEAR(s.date), MONTH(s.date), QUARTER(s.date), WEEK(s.date)


class OLAPManager:
    def __init__(self):
        self.conn = create_db_connection()
        
    def refresh_cube(self):
        """Refresh the OLAP cube by recalculating all aggregations"""
        try:
            cursor = self.conn.cursor()
            
            # Clear existing data
            cursor.execute("TRUNCATE TABLE sales_cube")

            cursor.execute("""
                INSERT INTO sales_cube (
                    product_id, product_name, category, 
                    sale_date, sale_year, sale_month, sale_quarter, sale_week,
                    total_sales, total_quantity, transaction_count, avg_sale
                )
                SELECT 
                    s.product_id,
                    p.name AS product_name,
                    p.category,
                    DATE(s.date) AS sale_date,
                    YEAR(s.date) AS sale_year,
                    MONTH(s.date) AS sale_month,
                    QUARTER(s.date) AS sale_quarter,
                    WEEK(s.date) AS sale_week,
                    SUM(s.total_amount) AS total_sales,
                    SUM(s.quantity) AS total_quantity,
                    COUNT(DISTINCT s.id) AS transaction_count,
                    AVG(s.total_amount) AS avg_sale
                FROM sales s
                JOIN products p ON s.product_id = p.id
                GROUP BY 
                    s.product_id, p.name, p.category, 
                    DATE(s.date), YEAR(s.date), MONTH(s.date), QUARTER(s.date), WEEK(s.date)
            """)
            
            self.conn.commit()
            
        except Error as e:
            self.conn.rollback()
            raise e
        finally:
            if self.conn.is_connected():
                cursor.close()
                
    def get_sales_report(self, group_by="category", start_date=None, end_date=None):
        """
        Get sales data grouped by specified dimension within date range
        Parameters:
            group_by: 'category', 'product', or 'day'
            start_date: datetime.date
            end_date: datetime.date
        """
        cursor = None
        try:
            cursor = self.conn.cursor(dictionary=True)
            
            # Determine grouping column
            if group_by.lower() == "category":
                group_col = "category"
            elif group_by.lower() == "product":
                group_col = "product_name"
            else:  # day
                group_col = "sale_date"
                
            # Build query
            query = f"""
                SELECT 
                    {group_col} AS group_name,
                    SUM(total_sales) AS total_sales,
                    SUM(total_quantity) AS total_quantity,
                    SUM(transaction_count) AS transaction_count,
                    SUM(total_sales)/SUM(transaction_count) AS avg_sale
                FROM sales_cube
                WHERE sale_date BETWEEN %s AND %s
                GROUP BY {group_col}
                ORDER BY {group_col}, total_sales DESC
            """
            
            # Execute with date parameters
            cursor.execute(query, (start_date, end_date))
            results = cursor.fetchall()
            
            # Format results into tuples
            formatted_results = []
            for row in results:
                formatted_results.append((
                    str(row['group_name']),
                    float(row['total_sales']),
                    float(row['total_quantity']),
                    int(row['transaction_count']),
                    float(row['avg_sale']) if row['avg_sale'] else 0.0
                ))
                
            return formatted_results
            
        except Error as e:
            raise e
        finally:
            if self.conn.is_connected() and cursor:
                cursor.close()




# ----------------------------
# Hashing and Verifying Password
# ----------------------------

def hash_password(password):
    """Hashes the password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(stored_password, provided_password):
    """Verifies a stored password against one provided by user."""
    return stored_password == hash_password(provided_password)

# ----------------------------
# User Management UI
# ----------------------------

class UserManagementUI:
    def __init__(self, parent):
        self.parent = parent
        self.create_widgets()
        self.populate_users()

    def create_widgets(self):
        # Labels and Entry fields
        tk.Label(self.parent, text="Username").grid(row=0, column=0, padx=10, pady=5, sticky='w')
        self.username_entry = tk.Entry(self.parent)
        self.username_entry.grid(row=0, column=1, padx=10, pady=5)

        tk.Label(self.parent, text="Password").grid(row=1, column=0, padx=10, pady=5, sticky='w')
        self.password_entry = tk.Entry(self.parent, show="*")
        self.password_entry.grid(row=1, column=1, padx=10, pady=5)

        tk.Label(self.parent, text="Role").grid(row=2, column=0, padx=10, pady=5, sticky='w')
        self.role_var = tk.StringVar()
        self.role_var.set("cashier")
        role_options = ["cashier", "manager", "admin"]  # Added "admin" option
        self.role_menu = ttk.Combobox(self.parent, textvariable=self.role_var, 
                                     values=role_options, state="readonly")
        self.role_menu.grid(row=2, column=1, padx=10, pady=5, sticky='w')

        tk.Label(self.parent, text="Assign Tabs").grid(row=3, column=0, padx=10, pady=5, sticky='nw')
        self.tabs_frame = tk.Frame(self.parent)
        self.tabs_frame.grid(row=3, column=1, padx=10, pady=5, sticky='w')

        # Define available tabs
        self.available_tabs = [
            "Product Management",
            "Inventory Management",
            "Sales Processing",
            "Sales Reports",
            "Billing",
            "User Management",
            "Enhanced Sales Report",  # New tab
            "OLAP Analysis",         # New tab
            "Price History",
            "Demand Forecasting"        # New tab
        ]

        # Create a checkbox for each tab - modified to use 3 columns
        self.tab_vars = {}
        for idx, tab in enumerate(self.available_tabs):
            var = tk.IntVar()
            chk = tk.Checkbutton(self.tabs_frame, text=tab, variable=var, 
                                bg="#f0f0f0", anchor='w')  # Match existing style
            # Calculate row and column for 3-column layout
            row = idx // 3
            col = idx % 3
            chk.grid(row=row, column=col, sticky='w', padx=5, pady=2)
            self.tab_vars[tab] = var

        # Buttons
        tk.Button(self.parent, text="Add User", command=self.add_user).grid(row=4, column=0, padx=10, pady=10)
        tk.Button(self.parent, text="Update User", command=self.update_user).grid(row=4, column=1, padx=10, pady=10)
        tk.Button(self.parent, text="Delete User", command=self.delete_user).grid(row=4, column=2, padx=10, pady=10)

        # Users List (Treeview)
        columns = ("ID", "Username", "Role", "Tabs")
        self.tree = ttk.Treeview(self.parent, columns=columns, show='headings')
        for col in columns:
            self.tree.heading(col, text=col, anchor='w')
            if col == "Tabs":
                self.tree.column(col, width=250)
            elif col == "Username":
                self.tree.column(col, width=150)
            else:
                self.tree.column(col, width=100)
        self.tree.grid(row=5, column=0, columnspan=3, padx=10, pady=10, sticky='nsew')

        # Configure grid weights for responsiveness
        self.parent.grid_rowconfigure(5, weight=1)
        self.parent.grid_columnconfigure(2, weight=1)

        # Scrollbar for the Treeview
        scrollbar = ttk.Scrollbar(self.parent, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=5, column=3, sticky='ns')

        # Bind the treeview select
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

    def populate_users(self):
        # Clear the treeview
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Fetch data from the database
        try:
            conn = create_db_connection()
            if conn is None:
                messagebox.showerror("Database Error", "Could not connect to database")
                return
                
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, role, tabs FROM users")
            rows = cursor.fetchall()

            # Insert data into the treeview
            for row in rows:
                self.tree.insert("", tk.END, values=row)
                
        except Error as e:
            messagebox.showerror("Database Error", f"Error fetching users: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def add_user(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        role = self.role_var.get()
        tabs = [tab for tab, var in self.tab_vars.items() if var.get() == 1]  # Collect selected tabs

        if not username or not password or not role or not tabs:
            messagebox.showerror("Input Error", "All fields are required and at least one tab must be assigned.")
            return

        hashed_password = hash_password(password)
        tabs_str = ",".join(tabs)  # Convert tabs list to a string for storage

        try:
            conn = create_db_connection()
            if conn is None:
                messagebox.showerror("Database Error", "Could not connect to database")
                return
                
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users 
                (username, password, role, tabs) 
                VALUES (%s, %s, %s, %s)
            """, (username, hashed_password, role, tabs_str))
            
            conn.commit()
            messagebox.showinfo("Success", "User added successfully.")
            self.populate_users()
            self.clear_entries()
            
        except Error as e:
            if e.errno == 1062:  # MySQL duplicate entry error code
                messagebox.showerror("Error", "Username already exists.")
            else:
                messagebox.showerror("Database Error", f"Error adding user: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def update_user(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Selection Error", "No user selected.")
            return

        item = self.tree.item(selected_item)
        user_id = item['values'][0]

        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        role = self.role_var.get()
        tabs = [tab for tab, var in self.tab_vars.items() if var.get() == 1]

        if not username or not role or not tabs:
            messagebox.showerror("Input Error", "Username and Role are required, and at least one tab must be assigned.")
            return

        try:
            conn = create_db_connection()
            if conn is None:
                messagebox.showerror("Database Error", "Could not connect to database")
                return
                
            cursor = conn.cursor()
            
            if password:
                hashed_password = hash_password(password)
                cursor.execute("""
                    UPDATE users 
                    SET username = %s, password = %s, role = %s, tabs = %s 
                    WHERE id = %s
                """, (username, hashed_password, role, ",".join(tabs), user_id))
            else:
                cursor.execute("""
                    UPDATE users 
                    SET username = %s, role = %s, tabs = %s 
                    WHERE id = %s
                """, (username, role, ",".join(tabs), user_id))
                
            conn.commit()
            messagebox.showinfo("Success", "User updated successfully.")
            self.populate_users()
            self.clear_entries()
            
        except Error as e:
            if e.errno == 1062:  # MySQL duplicate entry error code
                messagebox.showerror("Error", "Username already exists.")
            else:
                messagebox.showerror("Database Error", f"Error updating user: {e}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def delete_user(self):
        selected_item = self.tree.selection()
        if not selected_item:
            messagebox.showerror("Selection Error", "No user selected.")
            return

        item = self.tree.item(selected_item)
        user_id = item['values'][0]

        if messagebox.askyesno("Confirmation", "Are you sure you want to delete this user?"):
            try:
                conn = create_db_connection()
                if conn is None:
                    messagebox.showerror("Database Error", "Could not connect to database")
                    return
                    
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
                conn.commit()
                messagebox.showinfo("Success", "User deleted successfully.")
                self.populate_users()
                
            except Error as e:
                messagebox.showerror("Database Error", f"Error deleting user: {e}")
            finally:
                if conn and conn.is_connected():
                    cursor.close()
                    conn.close()

    def on_tree_select(self, event):
        selected_item = self.tree.selection()
        if not selected_item:
            return

        item = self.tree.item(selected_item)
        user_id, username, role, tabs = item['values']

        self.username_entry.delete(0, tk.END)
        self.username_entry.insert(tk.END, username)
        self.role_var.set(role)

        # Reset all tab checkboxes
        for var in self.tab_vars.values():
            var.set(0)

        # Set selected tabs
        selected_tabs = tabs.split(',')
        for tab in selected_tabs:
            if tab in self.tab_vars:
                self.tab_vars[tab].set(1)

    def clear_entries(self):
        self.username_entry.delete(0, tk.END)
        self.password_entry.delete(0, tk.END)
        self.role_var.set("cashier")
        for var in self.tab_vars.values():
            var.set(0)



class PriceHistoryUI:
    def __init__(self, parent):
        self.parent = parent
        self.create_widgets()
        self.load_history()

    def create_widgets(self):
        # Configure main frame
        self.parent.grid_rowconfigure(1, weight=1)
        self.parent.grid_columnconfigure(0, weight=1)
        
        # Filter controls frame
        filter_frame = tk.Frame(self.parent, bg="#f0f0f0", padx=10, pady=10)
        filter_frame.grid(row=0, column=0, sticky="ew")
        
        # Product ID filter
        tk.Label(filter_frame, text="Product ID:", bg="#f0f0f0").grid(row=0, column=0, padx=5, sticky='e')
        self.product_id_entry = tk.Entry(filter_frame, width=10, bd=2, relief=tk.GROOVE)
        self.product_id_entry.grid(row=0, column=1, padx=5, sticky='w')
        
        # OR separator
        tk.Label(filter_frame, text="OR", bg="#f0f0f0", fg="gray").grid(row=0, column=2, padx=5)
        
        # Date From filter
        tk.Label(filter_frame, text="From:", bg="#f0f0f0").grid(row=0, column=3, padx=5, sticky='e')
        self.date_from_entry = DateEntry(
            filter_frame,
            width=12,
            background='darkblue',
            foreground='white',
            borderwidth=2,
            date_pattern='yyyy-mm-dd'
        )
        self.date_from_entry.grid(row=0, column=4, padx=5, sticky='w')
        self.date_from_entry.set_date(datetime.now() - timedelta(days=30))  # Default to 30 days ago
        
        # Date To filter
        tk.Label(filter_frame, text="To:", bg="#f0f0f0").grid(row=0, column=5, padx=5, sticky='e')
        self.date_to_entry = DateEntry(
            filter_frame,
            width=12,
            background='darkblue',
            foreground='white',
            borderwidth=2,
            date_pattern='yyyy-mm-dd'
        )
        self.date_to_entry.grid(row=0, column=6, padx=5, sticky='w')
        self.date_to_entry.set_date(datetime.now())  # Default to today
        
        # Buttons
        button_frame = tk.Frame(filter_frame, bg="#f0f0f0")
        button_frame.grid(row=0, column=7, columnspan=3, padx=10)
        
        tk.Button(button_frame, text="Filter", command=self.load_history,
                bg="#4CAF50", fg="white", bd=0, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="Clear", command=self.clear_filters,
                bg="#f44336", fg="white", bd=0, padx=10).pack(side=tk.LEFT, padx=2)
        tk.Button(button_frame, text="Export", command=self.export_csv,
                bg="#2196F3", fg="white", bd=0, padx=10).pack(side=tk.LEFT, padx=2)

        # Treeview frame
        tree_frame = tk.Frame(self.parent)
        tree_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        
        # History Treeview
        columns = ("ID", "Product ID", "Product", "Old Price", "New Price", "Change", "Changed By", "Date")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show='headings', height=20)
        
        # Configure columns
        col_widths = [50, 80, 150, 90, 90, 90, 120, 150]
        col_anchors = ['center', 'center', 'w', 'e', 'e', 'e', 'center', 'center']
        
        for idx, col in enumerate(columns):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=col_widths[idx], anchor=col_anchors[idx])
        
        # Add scrollbar
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        
        # Grid layout
        self.tree.grid(row=0, column=0, sticky='nsew')
        scrollbar.grid(row=0, column=1, sticky='ns')
        
        # Configure tag colors for price changes
        self.tree.tag_configure('increase', foreground='#2E7D32')  # Dark green
        self.tree.tag_configure('decrease', foreground='#C62828')  # Dark red
        self.tree.tag_configure('nochange', foreground='#616161')  # Gray

    def clear_filters(self):
        """Clear all filter fields and reload"""
        self.product_id_entry.delete(0, tk.END)
        self.date_from_entry.set_date(datetime.now() - timedelta(days=30))
        self.date_to_entry.set_date(datetime.now())
        self.load_history()

    def load_history(self):
        # Clear existing data
        for row in self.tree.get_children():
            self.tree.delete(row)
        
        # Get filter values
        product_id = self.product_id_entry.get().strip()
        date_from = self.date_from_entry.get_date()
        date_to = self.date_to_entry.get_date()
        
        # Validate inputs
        if product_id and not product_id.isdigit():
            messagebox.showerror("Error", "Product ID must be a number")
            return
        
        # Build flexible query
        query = """
            SELECT 
                ph.id, 
                ph.product_id, 
                p.name,
                ph.old_price, 
                ph.new_price,
                ROUND(ph.new_price - ph.old_price, 2) as price_change,
                ph.changed_by, 
                DATE_FORMAT(ph.change_date, '%Y-%m-%d %H:%i')
            FROM price_history ph
            JOIN products p ON ph.product_id = p.id
            WHERE 1=1
        """
        params = []
        
        # Apply filters (can use either product ID or dates or both)
        if product_id:
            query += " AND ph.product_id = %s"
            params.append(int(product_id))
            
        if date_from:
            query += " AND ph.change_date >= %s"
            params.append(date_from.strftime("%Y-%m-%d 00:00:00"))
            
        if date_to:
            query += " AND ph.change_date <= %s"
            params.append(date_to.strftime("%Y-%m-%d 23:59:59"))
            
        # If no filters are applied, show last 30 days by default
        if not product_id and not date_from and not date_to:
            query += " AND ph.change_date >= %s"
            params.append((datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d 00:00:00"))
        
        query += " ORDER BY ph.change_date DESC"
        
        # Execute query
        conn = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            
            # Format and insert data into treeview
            for row in cursor.fetchall():
                price_change = row[5]
                
                # Format display values
                old_price = f"{row[3]:.2f}"
                new_price = f"{row[4]:.2f}"
                
                # Determine change display and tags
                if price_change > 0:
                    change_display = f"↑ {abs(price_change):.2f}"
                    tags = ('increase',)
                elif price_change < 0:
                    change_display = f"↓ {abs(price_change):.2f}"
                    tags = ('decrease',)
                else:
                    change_display = f"→ ${abs(price_change):.2f}"
                    tags = ('nochange',)
                
                self.tree.insert("", "end", values=(
                    row[0], row[1], row[2], 
                    old_price, new_price,
                    change_display, row[6], row[7]
                ), tags=tags)
                
        except Error as e:
            messagebox.showerror("Database Error", f"Failed to load price history:\n{str(e)}")
        finally:
            if conn and conn.is_connected():
                cursor.close()
                conn.close()

    def export_csv(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialfile=f"price_history_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
        )
        if not file_path:
            return
            
        try:
            with open(file_path, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                
                # Write headers
                headers = [self.tree.heading(col)['text'] for col in self.tree['columns']]
                writer.writerow(headers)
                
                # Write data (remove change arrows for clean CSV)
                for row_id in self.tree.get_children():
                    row_data = list(self.tree.item(row_id)['values'])
                    if row_data[5].startswith(('↑', '↓', '→')):
                        row_data[5] = row_data[5][2:].strip()
                    writer.writerow(row_data)
                
            messagebox.showinfo("Export Complete", f"Price history exported to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to export:\n{str(e)}")


# ----------------------------
# Login UI Class
# ----------------------------

class LoginUI:
    def __init__(self, master):
        self.master = master
        self.master.title("UET Cash & Carry - Login")
        self.master.geometry("1100x619")
        self.master.configure(bg="#f8f9fa")
        self.master.resizable(True, True)
        
        # Custom font styles
        self.title_font = ("Segoe UI", 32, "bold")
        self.subtitle_font = ("Segoe UI", 14)
        self.label_font = ("Segoe UI", 11)
        self.button_font = ("Segoe UI", 12, "bold")
        self.entry_font = ("Segoe UI", 12)
        
        # Create main container frame
        self.main_frame = tk.Frame(self.master, bg="#f8f9fa")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left side - Branding/Graphics (wider area)
        self.left_frame = tk.Frame(self.main_frame, bg="#6a5acd", width=450)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH)
        
        # Branding content
        brand_frame = tk.Frame(self.left_frame, bg="#6a5acd")
        brand_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        
        # Logo placeholder
        self.logo_label = tk.Label(brand_frame, text="🛒", font=("Arial", 72), bg="#6a5acd", fg="white")
        self.logo_label.pack(pady=(0, 30))
        
        # Brand name
        self.brand_label = tk.Label(brand_frame, text="UET CASH & CARRY", 
                                 font=self.title_font, fg="white", bg="#6a5acd")
        self.brand_label.pack(pady=(0, 15))
        
        # Tagline
        self.tagline_label = tk.Label(brand_frame, text="Premium Inventory Management System", 
                                   font=self.subtitle_font, fg="white", bg="#6a5acd")
        self.tagline_label.pack()
        
        # Right side - Login Form
        self.right_frame = tk.Frame(self.main_frame, bg="white", padx=50, pady=50)
        self.right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        
        # Login form title
        self.login_title = tk.Label(self.right_frame, text="Welcome Back!", 
                                  font=self.title_font, fg="#343a40", bg="white")
        self.login_title.pack(pady=(30, 15))
        
        # Login subtitle
        self.login_subtitle = tk.Label(self.right_frame, text="Sign in to access your dashboard", 
                                     font=self.subtitle_font, fg="#6c757d", bg="white")
        self.login_subtitle.pack(pady=(0, 50))
        
        # Username field
        self.username_frame = tk.Frame(self.right_frame, bg="white")
        self.username_frame.pack(fill=tk.X, pady=(0, 20))
        
        self.username_label = tk.Label(self.username_frame, text="Username", 
                                     font=self.label_font, fg="#495057", bg="white", anchor='w')
        self.username_label.pack(fill=tk.X)
        
        self.username_entry = tk.Entry(self.username_frame, font=self.entry_font, 
                                     bd=0, highlightthickness=1, highlightbackground="#ced4da",
                                     highlightcolor="#6a5acd", relief=tk.FLAT)
        self.username_entry.pack(fill=tk.X, ipady=10)
        self.add_placeholder(self.username_entry, "Enter your username")
        
        # Password field with special placeholder handling
        self.password_frame = tk.Frame(self.right_frame, bg="white")
        self.password_frame.pack(fill=tk.X, pady=(0, 15))
        
        self.password_label = tk.Label(self.password_frame, text="Password", 
                                     font=self.label_font, fg="#495057", bg="white", anchor='w')
        self.password_label.pack(fill=tk.X)
        
        self.password_entry = tk.Entry(self.password_frame, font=self.entry_font, 
                                     bd=0, highlightthickness=1, 
                                     highlightbackground="#ced4da", highlightcolor="#6a5acd", 
                                     relief=tk.FLAT)
        self.password_entry.pack(fill=tk.X, ipady=10)
        self.add_password_placeholder()
        
        # Show password checkbox
        self.show_password_frame = tk.Frame(self.right_frame, bg="white")
        self.show_password_frame.pack(fill=tk.X, pady=(0, 40))
        
        self.show_password_var = tk.BooleanVar()
        self.show_password_button = tk.Checkbutton(self.show_password_frame, 
                                                  text="Show Password",
                                                  variable=self.show_password_var,
                                                  command=self.toggle_password_visibility,
                                                  bg="white", fg="#495057",
                                                  selectcolor="white",
                                                  activebackground="white",
                                                  activeforeground="#495057",
                                                  font=self.label_font)
        self.show_password_button.pack(side=tk.LEFT)
        
        # Login button
        self.login_button = tk.Button(self.right_frame, text="LOGIN", 
                                    font=self.button_font, bg="#6a5acd", fg="white",
                                    activebackground="#5b4bbb", activeforeground="white",
                                    bd=0, padx=25, pady=12, cursor="hand2",
                                    command=self.login)
        self.login_button.pack(fill=tk.X, pady=(0, 30))
        
        
        # Add some visual elements
        self.add_decorative_elements()
        
    def add_decorative_elements(self):
        """Add subtle decorative elements"""
        separator = tk.Frame(self.right_frame, height=2, bg="#e9ecef")
        separator.pack(fill=tk.X, pady=25)
        self.right_frame.config(highlightbackground="#e9ecef", highlightthickness=1)
        
    def add_placeholder(self, entry, placeholder):
        """Add placeholder to regular entry fields"""
        entry.insert(0, placeholder)
        entry.config(fg="#adb5bd")
        
        def on_focus_in(event):
            if entry.get() == placeholder:
                entry.delete(0, "end")
                entry.config(fg="#495057")
                entry.config(highlightbackground="#6a5acd")
                
        def on_focus_out(event):
            if not entry.get():
                entry.insert(0, placeholder)
                entry.config(fg="#adb5bd")
                entry.config(highlightbackground="#ced4da")
                
        entry.bind("<FocusIn>", on_focus_in)
        entry.bind("<FocusOut>", on_focus_out)
        entry.config(highlightbackground="#ced4da")

    def add_password_placeholder(self):
        """Special placeholder handling for password field"""
        placeholder = "Enter your password"
        self.password_entry.insert(0, placeholder)
        self.password_entry.config(fg="#adb5bd", show="")
        
        def on_focus_in(event):
            if self.password_entry.get() == placeholder:
                self.password_entry.delete(0, "end")
                self.password_entry.config(fg="#495057", show="*")
                
        def on_focus_out(event):
            if not self.password_entry.get():
                self.password_entry.insert(0, placeholder)
                self.password_entry.config(fg="#adb5bd", show="")
                if self.show_password_var.get():
                    self.password_entry.config(show="")
                
        self.password_entry.bind("<FocusIn>", on_focus_in)
        self.password_entry.bind("<FocusOut>", on_focus_out)
        self.password_entry.config(highlightbackground="#ced4da")

    def toggle_password_visibility(self):
        """Toggle password visibility while respecting placeholder"""
        current_text = self.password_entry.get()
        placeholder = "Enter your password"
        
        if current_text == placeholder:
            return  # Don't show asterisks for placeholder
            
        if self.show_password_var.get():
            self.password_entry.config(show="")
        else:
            self.password_entry.config(show="*")

 

    def login(self):
        """Handle login process"""
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        
        # Remove placeholder text if still present
        if username == "Enter your username":
            username = ""
        if password == "Enter your password":
            password = ""
    
        # Connect to the database and check credentials
        conn = None
        cursor = None
        try:
            conn = create_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, password, role, tabs FROM users WHERE username = %s", (username,))
            user = cursor.fetchone()
            
            if user and verify_password(user[1], password):
                self.role = user[2]
                self.tabs = user[3].split(",") if user[3] else []
                messagebox.showinfo("Login Success", "Welcome!")
                self.master.destroy()
                self.open_main_application()
            else:
                messagebox.showerror("Login Failed", "Invalid username or password.")
                self.shake_login_form()
                
        except Error as e:
            messagebox.showerror("Database Error", f"Error during login: {e}")
        finally:
            if cursor:
                cursor.close()
            if conn and conn.is_connected():
                conn.close()

    def open_main_application(self):
        """Open the main application after successful login"""
        main_window = tk.Tk()
        main_window.title("UET Cash & Carry - Dashboard")
        main_window.geometry("800x500")
       

        # Create a Notebook (tabbed interface)
        self.tab_control = ttk.Notebook(main_window)

        # Create frames for each functionality
        if "Product Management" in self.tabs:
            self.product_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.product_tab, text="📦 Product Management")
            ProductManagementUI(self.product_tab)

        if "Inventory Management" in self.tabs:
            self.inventory_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.inventory_tab, text="📊 Inventory Management")
            InventoryManagementUI(self.inventory_tab)

        if "Sales Processing" in self.tabs:
            self.sales_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.sales_tab, text="💸 Sales Processing")
            SalesProcessingUI(self.sales_tab)

        if "Sales Reports" in self.tabs:
            self.reports_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.reports_tab, text="📈 Sales Reports")
            SalesReportUI(self.reports_tab)

        if "Enhanced Sales Report" in self.tabs:
            self.sales_report_tab = ttk.Frame(self.tab_control)
            self.tab_control.add(self.sales_report_tab, text="📊 Sales Analytics")
            EnhancedSalesReportUI(self.sales_report_tab)

        if "OLAP Analysis" in self.tabs:
            self.olap_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.olap_tab, text="🧮 OLAP Analysis")
            OLAPAnalysisUI(self.olap_tab)

        if "Billing" in self.tabs:
            self.billing_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.billing_tab, text="🧾 Billing")
            BillingUI(self.billing_tab)

        if "Price History" in self.tabs:
            self.price_history_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.price_history_tab, text="📅 Price History")
            PriceHistoryUI(self.price_history_tab)

        if "User Management" in self.tabs:
            self.user_management_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.user_management_tab, text="👥 User Management")
            UserManagementUI(self.user_management_tab)

        # Add this with the other tab conditions in open_main_application()
        if "Demand Forecasting" in self.tabs:
            self.forecast_tab = tk.Frame(self.tab_control)
            self.tab_control.add(self.forecast_tab, text="🔮 Demand Forecasting")
            DemandForecastingUI(self.forecast_tab)
    
        self.logout_tab = tk.Frame(self.tab_control, bg="#2b2b2b")
        self.tab_control.add(self.logout_tab, text="Credits") 
             
        # Title Label
        title_label = tk.Label(self.logout_tab, text="Point of Sale System", font=("Arial", 36, "bold"), fg="yellow", bg="#2b2b2b")
        title_label.pack(pady=(10, 0), padx=10)
    
        # Subtitle Label
        subtitle_label = tk.Label(self.logout_tab, text="(ADBMS Project)", font=("Arial", 16), fg="white", bg="#2b2b2b")
        subtitle_label.pack(pady=(0, 10), padx=10)
    
        # Section Heading
        section_heading_label = tk.Label(self.logout_tab, text=" Designed By:", font=("Arial", 18, "bold"), fg="white", bg="#2b2b2b")
        section_heading_label.pack(anchor='w', pady=(10, 0), padx=10)
    
        # Authors
        authors = [
            "  • Tahir Zaka Butt & Muhammad Yahya Khan"
        ]
        for author in authors:
            author_label = tk.Label(self.logout_tab, text=author, font=("Arial", 14), fg="white", bg="#2b2b2b")
            author_label.pack(anchor='w', pady=(0, 0), padx=10)
    
        # Presented To Section
        presented_to_label = tk.Label(self.logout_tab, text="\n Presented To:", font=("Arial", 18, "bold"), fg="white", bg="#2b2b2b")
        presented_to_label.pack(anchor='w', pady=(10, 0), padx=10)
    
        # Recipient
        recipient_label = tk.Label(self.logout_tab, text="  • Miss Farwa", font=("Arial", 14), fg="white", bg="#2b2b2b")
        recipient_label.pack(anchor='w', pady=(0, 10), padx=10)
    
        # Footer Label
        footer_label = tk.Label(self.logout_tab, text="\n\n\nUniversity of Engineering and Technology, Lahore", font=("Arial", 16, "bold"), fg="white", bg="#2b2b2b")
        footer_label.pack(pady=(10, 20))
    
        # Create the logout button and change its size and color
        logout_button = tk.Button(self.logout_tab, text="Logout", command=lambda: self.logout(main_window), bg="red", fg="white", font=("Arial", 14, "bold"))  # Increased size and changed color
        logout_button.pack(pady=(10, 10))  # Pack the logout button above the footer label
        self.tab_control.pack(expand=1, fill="both")
        main_window.mainloop()

    def logout(self, main_window):
        """Handle logout process"""
        main_window.destroy()
        login_window = tk.Tk()
        LoginUI(login_window)
        login_window.mainloop()

def verify_password(stored_password, provided_password):
    """Verify a stored password against one provided by user"""
    return stored_password == hashlib.sha256(provided_password.encode()).hexdigest()


# ---------------------------- 
# Main Application Code
# ----------------------------

if __name__ == "__main__":
    init_db()
    root = tk.Tk()
    login_ui = LoginUI(root)
    root.mainloop()
