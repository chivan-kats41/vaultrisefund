// Load products for each tab
function loadProducts(categoryId) {
    const container = document.getElementById('product_type_' + categoryId);
    
    // Check if products exist (passed from Django context)
    if (typeof products === 'undefined' || products.length === 0) {
        container.innerHTML = `
            <div class='none_data'>
                <img class="none_image" src="/static/v2/img/order/none_order.png">
                <p class="none_text">No products available</p>
            </div>
        `;
        return;
    }
    
    // Filter products by category ID
    const filteredProducts = products.filter(p => p.category_id === parseInt(categoryId));
    
    if (filteredProducts.length === 0) {
        container.innerHTML = `
            <div class='none_data'>
                <img class="none_image" src="/static/v2/img/order/none_order.png">
                <p class="none_text">No products in this category</p>
            </div>
        `;
        return;
    }
    
    container.innerHTML = filteredProducts.map(item => `
        <div class="product_card">
            <div class="product_content">
                <div class="product_title d-flex align-items-center">
                    <img class="product_image" src="${item.image}" alt="${item.product_name}">
                    <div class="flex-grow-1">
                        <div class="product_name">${item.product_name}</div>
                        <div class="product_vip">
                            <img src="/static/v2/img/common/vip_icon.png" style="width: 16px; height: 16px;">
                            <span>VIP${item.minimum_vip_level}</span>
                        </div>
                    </div>
                </div>
                <div class="product_info">
                    <div class="product_item d-flex justify-content-between">
                        <p class="label">Revenue</p>
                        <p class="value">${item.revenue_days} Days</p>
                    </div>
                    <div class="product_item d-flex justify-content-between">
                        <p class="label">Daily Earnings</p>
                        <p class="value">${item.currency} ${item.daily_income}</p>
                    </div>
                    <div class="product_item d-flex justify-content-between">
                        <p class="label">Total Revenue</p>
                        <p class="value">${item.currency} ${item.total_income}</p>
                    </div>
                </div>
                <div class="product_page_buy_btn" onclick='buyDialog(${JSON.stringify(item).replace(/'/g, "&apos;")})'>
                    <p style="width: 48%; text-align: center; color: white;">${item.currency} ${item.price}</p>
                    <p style="width: 48%; text-align: center;">Invest Now</p>
                </div>
            </div>
        </div>
    `).join('');
}

// Switch tabs
function switchTab(categoryId) {
    // Update nav active state
    document.querySelectorAll('.nav').forEach(nav => nav.classList.remove('nav_active'));
    const activeNav = document.querySelector(`.nav[data-type="${categoryId}"]`);
    if (activeNav) {
        activeNav.classList.add('nav_active');
    }
    
    // Show/hide product lists
    document.querySelectorAll('.product_list').forEach(list => list.classList.add('d-none'));
    const targetList = document.getElementById('product_type_' + categoryId);
    if (targetList) {
        targetList.classList.remove('d-none');
    }
    
    // Load products if not already loaded
    loadProducts(categoryId);
}

// Open buy dialog
function buyDialog(product) {
    // Set product ID
    const productIdInput = document.getElementById('product_id');
    if (productIdInput) {
        productIdInput.value = product.id;
    }
    
    // Update dialog with product information
    const updateElement = (selector, value) => {
        const el = document.querySelector(selector);
        if (el) {
            if (el.tagName === 'IMG') {
                el.src = value;
            } else {
                el.textContent = value;
            }
        }
    };
    
    updateElement('.product_dialog_image', product.image);
    updateElement('.product_title', product.product_name);
    updateElement('.vip_level', 'VIP' + product.minimum_vip_level);
    updateElement('.product_price', product.currency + ' ' + product.price);
    updateElement('.product_days', product.revenue_days);
    updateElement('.product_daily_income', product.currency + ' ' + product.daily_income);
    updateElement('.product_total_income', product.currency + ' ' + product.total_income);
    updateElement('.product_pay_money', product.currency + ' ' + product.price);
    updateElement('.product_pay_total_income', product.currency + ' ' + product.total_income);
    
    // Show modal
    const modalElement = document.getElementById('productModal');
    if (modalElement && typeof bootstrap !== 'undefined') {
        const modal = new bootstrap.Modal(modalElement);
        modal.show();
    }
}

// Invest now action
function investNow() {
    const productId = document.getElementById('product_id').value;
    
    if (!productId) {
        alert('Please select a product');
        return;
    }
    
    // Submit form or make AJAX request to Django backend
    // Example with form submission:
    const form = document.getElementById('investForm');
    if (form) {
        form.submit();
    } else {
        // Or make AJAX request
        fetch('/invest/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ product_id: productId })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                alert('Investment submitted successfully!');
                location.reload();
            } else {
                alert('Error: ' + data.message);
            }
        })
        .catch(error => {
            console.error('Error:', error);
            alert('An error occurred. Please try again.');
        });
    }
}

// Helper function to get CSRF token
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    // Load first category's products
    if (typeof categories !== 'undefined' && categories.length > 0) {
        loadProducts(categories[0].id);
    } else if (typeof products !== 'undefined' && products.length > 0) {
        loadProducts(products[0].category_id);
    }
});