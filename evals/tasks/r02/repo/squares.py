def even_squares(nums):
    out = []
    for n in nums:
        if n % 2 == 0:
            out.append(n * n)
    return out
