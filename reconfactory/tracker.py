"""Product identity, location, and lifecycle tracking."""

from __future__ import annotations

from collections.abc import Iterable

from .models import Product, ProductRecipe, ProductStatus, QualityStatus


class ProductTracker:
    def __init__(self, recipes: dict[str, ProductRecipe]) -> None:
        self.recipes = recipes
        self._products: dict[str, Product] = {}
        self._counter = 0

    def create_product(
        self, product_type: str, defect_flags: Iterable[str] | None = None
    ) -> Product:
        if product_type not in self.recipes:
            raise KeyError(f"Unknown product type: {product_type}")
        self._counter += 1
        recipe = self.recipes[product_type]
        product = Product(
            product_id=f"P-{self._counter:05d}",
            product_type=recipe.product_type,
            display_name=recipe.display_name,
            required_processes=list(recipe.required_processes),
            defect_flags=list(defect_flags or []),
        )
        self._products[product.product_id] = product
        return product

    def get(self, product_id: str) -> Product:
        return self._products[product_id]

    def all(self) -> list[Product]:
        return list(self._products.values())

    def move(self, product_id: str, location: str) -> Product:
        product = self.get(product_id)
        if product.status in {ProductStatus.COMPLETED, ProductStatus.REJECTED}:
            raise ValueError(f"Cannot move finalized product {product_id}")
        product.current_location = location
        product.route.append(location)
        product.mark_updated()
        return product

    def update_status(self, product_id: str, status: ProductStatus) -> Product:
        product = self.get(product_id)
        product.status = status
        product.mark_updated()
        return product

    def assign_station(self, product_id: str, station_id: str | None) -> Product:
        product = self.get(product_id)
        product.assigned_station = station_id
        product.mark_updated()
        return product

    def complete_process(self, product_id: str, process: str) -> Product:
        product = self.get(product_id)
        if process and process not in product.completed_processes:
            product.completed_processes.append(process)
        product.assigned_station = None
        product.mark_updated()
        return product

    def pause(self, product_id: str, reason: str) -> Product:
        product = self.get(product_id)
        product.status = ProductStatus.PAUSED
        product.assigned_station = None
        product.recovery_notes.append(reason)
        product.mark_updated()
        return product

    def queue(self, product_id: str, location: str = "processing_buffer") -> Product:
        product = self.get(product_id)
        product.status = ProductStatus.QUEUED
        product.assigned_station = None
        product.current_location = location
        product.route.append(location)
        product.mark_updated()
        return product

    def mark_quality(
        self, product_id: str, accepted: bool, reason: str | None = None
    ) -> Product:
        product = self.get(product_id)
        product.assigned_station = None
        product.quality = QualityStatus.ACCEPTED if accepted else QualityStatus.REJECTED
        product.status = ProductStatus.COMPLETED if accepted else ProductStatus.REJECTED
        product.current_location = "accepted_output" if accepted else "reject_output"
        product.defect_reason = reason
        product.route.append(product.current_location)
        product.mark_updated()
        return product

    def by_status(self, status: ProductStatus) -> list[Product]:
        return [product for product in self._products.values() if product.status == status]
