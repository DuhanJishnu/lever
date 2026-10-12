class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        return (
            isinstance(other, Point)
            and (self.x, self.y) == (other.x, other.y)
        )
