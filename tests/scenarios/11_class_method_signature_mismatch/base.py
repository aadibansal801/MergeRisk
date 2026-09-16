class InvoiceService:
    def compute_total(self, price, quantity):
        return price * quantity

    def summarize(self, price, quantity):
        total = self.compute_total(price, quantity)
        return f"Total due: {total}"
