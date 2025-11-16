import csv

def derive_masks_from_csv(csv_path):
    """
    Derive 8-bit checksum masks from a CSV with columns:
      - Byte1, Byte2, Byte5, Checksum_Byte6  (decimal)
    Returns (M1, M2, M5), each a list of 8 bytes:
      Mx[bit] = mask applied to that byte for checksum bit 'bit'.
    """

    # --- 1. Load data --------------------------------------------------------
    rows = []       # each row: 24-bit input vector (b1,b2,b5 bits)
    ys = [[] for _ in range(8)]  # one list per checksum bit

    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            b1 = int(r["Byte1"])
            b2 = int(r["Byte2"])
            b5 = int(r["Byte5"])
            c  = int(r["Checksum_Byte6"])

            # Build 24-bit input vector (bits of b1,b2,b5, LSB-first)
            x = []
            for byte in (b1, b2, b5):
                for k in range(8):
                    x.append((byte >> k) & 1)
            rows.append(x)

            # Output bits of checksum
            for bit in range(8):
                ys[bit].append((c >> bit) & 1)

    # --- 2. Solve linear systems over GF(2) ---------------------------------
    def solve_gf2(A, b):
        """
        Solve A x = b over GF(2) using Gaussian elimination.
        A: list of m rows, each length n (0/1 ints)
        b: list length m (0/1 ints)
        Returns one solution x (list length n of 0/1) or raises ValueError.
        """
        m, n = len(A), len(A[0])
        M = [A[i][:] + [b[i]] for i in range(m)]  # augmented matrix
        pivots = [-1] * n
        row = 0

        for col in range(n):
            # find pivot
            pivot_row = None
            for r in range(row, m):
                if M[r][col] == 1:
                    pivot_row = r
                    break
            if pivot_row is None:
                continue

            # swap into position
            M[row], M[pivot_row] = M[pivot_row], M[row]
            pivots[col] = row

            # eliminate other rows
            for r in range(m):
                if r != row and M[r][col] == 1:
                    M[r] = [M[r][c] ^ M[row][c] for c in range(n + 1)]

            row += 1
            if row == m:
                break

        # check consistency
        for r in range(m):
            if all(M[r][c] == 0 for c in range(n)) and M[r][n] == 1:
                raise ValueError("No solution over GF(2)")

        # back-substitute (free vars = 0)
        x = [0] * n
        for col in reversed(range(n)):
            r = pivots[col]
            if r == -1:
                x[col] = 0
            else:
                s = M[r][n]
                for c in range(col + 1, n):
                    if M[r][c]:
                        s ^= x[c]
                x[col] = s

        return x

    masks = []
    for bit in range(8):
        sol = solve_gf2(rows, ys[bit])
        masks.append(sol)

    # --- 3. Convert 24-bit masks to per-byte masks ---------------------------
    M1, M2, M5 = [], [], []
    for bit in range(8):
        mask = masks[bit]

        # bits 0..7 -> Byte1, 8..15 -> Byte2, 16..23 -> Byte5 (LSB-first)
        b1_mask = sum(mask[k]       << k for k in range(8))
        b2_mask = sum(mask[8 + k]   << k for k in range(8))
        b5_mask = sum(mask[16 + k]  << k for k in range(8))

        M1.append(b1_mask)
        M2.append(b2_mask)
        M5.append(b5_mask)

    return M1, M2, M5


def build_checksum_func(M1, M2, M5):
    """
    Given masks M1,M2,M5 from derive_masks_from_csv, return a checksum(b1,b2,b5) function.
    """

    def parity8(x):
        x ^= x >> 4
        x ^= x >> 2
        x ^= x >> 1
        return x & 1

    def checksum(b1, b2, b5):
        c = 0
        for bit in range(8):
            p = (
                parity8(b1 & M1[bit]) ^
                parity8(b2 & M2[bit]) ^
                parity8(b5 & M5[bit])
            )
            c |= (p << bit)
        return c & 0xFF

    return checksum


if __name__ == "__main__":
    # Example usage with your file name
    csv_path = "checksum_lookup_table.csv"  # adjust path as needed

    M1, M2, M5 = derive_masks_from_csv(csv_path)
    print("M1 =", [f"0x{v:02X}" for v in M1])
    print("M2 =", [f"0x{v:02X}" for v in M2])
    print("M5 =", [f"0x{v:02X}" for v in M5])

    checksum = build_checksum_func(M1, M2, M5)

    # quick sanity check on the first few rows of the CSV
    with open(csv_path, newline='') as f:
        reader = csv.DictReader(f)
        for i, r in enumerate(reader):
            b1 = int(r["Byte1"])
            b2 = int(r["Byte2"])
            b5 = int(r["Byte5"])
            c  = int(r["Checksum_Byte6"])
            calc = checksum(b1, b2, b5)
            print(f"Row {i}: calc=0x{calc:02X}, expected=0x{c:02X}")
            if i >= 4:
                break
