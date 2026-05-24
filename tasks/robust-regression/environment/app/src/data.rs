use std::collections::HashMap;
use std::fs;

pub struct DataSet {
    pub headers: Vec<String>,
    pub rows: Vec<HashMap<String, f64>>,
    pub n_rows: usize,
}

pub fn load_csv(path: &str) -> DataSet {
    let content = fs::read_to_string(path)
        .unwrap_or_else(|e| panic!("Failed to read CSV file {}: {}", path, e));

    let mut lines = content.lines();
    let header_line = lines.next().expect("CSV file is empty");
    let headers: Vec<String> = header_line.split(',').map(|s| s.trim().to_string()).collect();

    let mut rows = Vec::new();
    for line in lines {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        let vals: Vec<f64> = line
            .split(',')
            .map(|s| {
                s.trim()
                    .parse::<f64>()
                    .unwrap_or_else(|e| panic!("Invalid float '{}': {}", s.trim(), e))
            })
            .collect();

        if vals.len() != headers.len() {
            panic!(
                "Row has {} columns but header has {}",
                vals.len(),
                headers.len()
            );
        }

        let mut row = HashMap::new();
        for (h, v) in headers.iter().zip(vals.iter()) {
            row.insert(h.clone(), *v);
        }
        rows.push(row);
    }

    let n_rows = rows.len();
    DataSet {
        headers,
        rows,
        n_rows,
    }
}

pub fn build_design_matrix(
    data: &DataSet,
    predictors: &[&str],
    response: &str,
) -> (Vec<f64>, Vec<f64>) {
    let n = data.n_rows;
    let p = predictors.len() + 1; // +1 for intercept

    let mut x = vec![0.0; n * p];
    let mut y = vec![0.0; n];

    for (i, row) in data.rows.iter().enumerate() {
        x[i * p] = 1.0; // intercept
        for (j, pred) in predictors.iter().enumerate() {
            x[i * p + (predictors.len() - j)] = *row
                .get(*pred)
                .unwrap_or_else(|| panic!("Missing predictor column '{}'", pred));
        }
        y[i] = *row
            .get(response)
            .unwrap_or_else(|| panic!("Missing response column '{}'", response));
    }

    (x, y)
}
