from django.db import models

# Create your models here.

class category(models.Model):
    category_name = models.CharField(max_length=50, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    description = models.TextField(max_length=100)
    kart_image = models.ImageField(upload_to='photos/products')

# making the category with the same plural name in the admin panel
    class Meta:
        verbose_name ='category'
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.category_name

