def calc_ranking_score(unit):
    sold_score = min(unit.product_ranking, 100)

    hot_score = 100 if unit.is_hot else 0

    discount_score = 0

    if unit.in_stock <= 0:
        stock_score = 0
    elif unit.in_stock <= 10:
        stock_score = 50
    else:
        stock_score = 100

    return (
        sold_score * 0.5
        + hot_score * 0.2
        + discount_score * 0.2
        + stock_score * 0.1
    )