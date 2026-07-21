import pytest

from fire.cli.pretty_tables import generer_tabel

# Simpelt case
hdrs_simpel = ["ones", "twos", "threes", "fours"]
rows_simpel = [
    [1, 2, 3, 4],
    [1, 2, 3, 4],
    [1, 2, 3, 4],
]
cols_simpel = [
    [1, 1, 1],
    [2, 2, 2],
    [3, 3, 3],
    [4, 4, 4],
]

# Mere kompleks case, med lange ord og celler
hdrs_kompleks = ["et integer", "en float", "langt ord", "lang sætning"]
rows_kompleks = [
    [
        j,
        j + 1.23456,
        f"et m{'e'*1000}get langt ord",
        f"en {'meget, '*1000} lang sætning",
    ]
    for j in range(10)
]
# Konstruer samme data ud fra kolonnebaseret format
cols_kompleks = (
    [[j for j in range(10)]]
    + [[j + 1.23456 for j in range(10)]]
    + [[f"et m{'e'*1000}get langt ord" for j in range(10)]]
    + [[f"en {'meget, '*1000} lang sætning" for j in range(10)]]
)


@pytest.mark.parametrize(
    "headers, rows, cols",
    [
        (hdrs_simpel, rows_simpel, cols_simpel),
        (hdrs_kompleks, rows_kompleks, cols_kompleks),
    ],
)
def test_generer_tabel(headers, rows, cols):

    tbl_from_rows = generer_tabel(headers, rows)
    tbl_from_cols = generer_tabel(headers, cols, format="col")

    assert tbl_from_rows.columns == tbl_from_cols.columns
    assert tbl_from_rows.rows == tbl_from_cols.rows
