class InvoiceService:
    def compute_total(self, price, quantity, tax_rate):
        return price * quantity * (1 + tax_rate)

    def summarize(self, price, quantity):
        total = self.compute_total(price, quantity)
        return f"Invoice total: {total}"
