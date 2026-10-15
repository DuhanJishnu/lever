class Calculator:
    def __init__(self):
        self.total = 0

    def add(self, values):
        for v in values:
            if v > 0:
                self.total = v
        return self.total
