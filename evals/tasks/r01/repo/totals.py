def sum_even(nums):
    total = 0
    for n in nums:
        if n % 2 == 0:
            total += n
    return total


def sum_odd(nums):
    total = 0
    for n in nums:
        if n % 2 != 0:
            total += n
    return total
