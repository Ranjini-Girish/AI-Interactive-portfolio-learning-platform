/// Transpose an m×n matrix (flat row-major) into n×m.
pub fn transpose(a: &[f64], m: usize, n: usize) -> Vec<f64> {
    let mut t = vec![0.0; m * n];
    for i in 0..m {
        for j in 0..n {
            t[j * m + i] = a[i * n + j];
        }
    }
    t
}

/// Multiply A(m×n) × B(n×p) → C(m×p). All flat row-major.
pub fn multiply(a: &[f64], b: &[f64], m: usize, n: usize, p: usize) -> Vec<f64> {
    let mut c = vec![0.0; m * p];
    for i in 0..m {
        for j in 0..p {
            let mut s = 0.0;
            for k in 0..n {
                s += a[i * n + k] * b[k * p + j];
            }
            c[i * p + j] = s;
        }
    }
    c
}

/// Solve Ax = b using Gaussian elimination with partial pivoting.
pub fn solve(a: &[f64], b: &[f64], n: usize) -> Vec<f64> {
    let mut aug: Vec<Vec<f64>> = (0..n)
        .map(|i| {
            let mut row = Vec::with_capacity(n + 1);
            for j in 0..n {
                row.push(a[i * n + j]);
            }
            row.push(b[i]);
            row
        })
        .collect();

    for col in 0..n {
        let mut max_row = col;
        let mut max_val = aug[col][col].abs();
        for row in (col + 1)..n {
            let v = aug[row][col].abs();
            if v > max_val {
                max_val = v;
                max_row = row;
            }
        }
        aug.swap(col, max_row);

        let pivot = aug[col][col];
        if pivot.abs() < 1e-15 {
            continue;
        }

        for row in (col + 1)..n {
            let factor = aug[row][col] / pivot;
            for j in col..n {
                let val = aug[col][j];
                aug[row][j] -= factor * val;
            }
        }
    }

    let mut x = vec![0.0; n];
    for i in (0..n).rev() {
        let mut s = aug[i][n];
        for j in (i + 1)..n {
            s -= aug[i][j] * x[j];
        }
        if aug[i][i].abs() < 1e-15 {
            x[i] = 0.0;
        } else {
            x[i] = s / aug[i][i];
        }
    }
    x
}

/// Compute inverse of n×n matrix using Gauss-Jordan elimination.
pub fn inverse(a: &[f64], n: usize) -> Vec<f64> {
    let mut aug: Vec<Vec<f64>> = (0..n)
        .map(|i| {
            let mut row = vec![0.0; 2 * n];
            for j in 0..n {
                row[j] = a[i * n + j];
            }
            row[n + i] = 1.0;
            row
        })
        .collect();

    for col in 0..n {
        let mut max_row = col;
        let mut max_val = aug[col][col].abs();
        for row in (col + 1)..n {
            let v = aug[row][col].abs();
            if v > max_val {
                max_val = v;
                max_row = row;
            }
        }
        aug.swap(col, max_row);

        let pivot = aug[col][col];
        if pivot.abs() < 1e-15 {
            continue;
        }

        for j in 0..(2 * n) {
            aug[col][j] /= pivot;
        }

        for row in 0..n {
            if row == col {
                continue;
            }
            let factor = aug[row][col];
            for j in 0..(2 * n) {
                let val = aug[col][j];
                aug[row][j] -= factor * val;
            }
        }
    }

    let mut inv = vec![0.0; n * n];
    for i in 0..n {
        for j in 0..n {
            inv[i * n + j] = aug[i][n + j];
        }
    }
    inv
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_identity_inverse() {
        let a = vec![1.0, 0.0, 0.0, 1.0];
        let inv = inverse(&a, 2);
        assert!((inv[0] - 1.0).abs() < 1e-10);
        assert!((inv[3] - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_multiply_identity() {
        let a = vec![1.0, 2.0, 3.0, 4.0];
        let id = vec![1.0, 0.0, 0.0, 1.0];
        let c = multiply(&a, &id, 2, 2, 2);
        assert!((c[0] - 1.0).abs() < 1e-10);
        assert!((c[3] - 4.0).abs() < 1e-10);
    }
}
