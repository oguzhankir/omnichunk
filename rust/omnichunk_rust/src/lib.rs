use pyo3::prelude::*;

#[inline]
fn is_ascii_whitespace(byte: u8) -> bool {
    matches!(byte, b'\t' | b'\n' | 11 | 12 | b'\r' | b' ')
}

#[pyfunction]
fn preprocess_nws_cumsum_bytes(py: Python<'_>, data: &[u8]) -> Vec<i64> {
    let bytes = data.to_vec();
    py.allow_threads(move || {
        let mut out: Vec<i64> = Vec::with_capacity(bytes.len() + 1);
        out.push(0);

        let mut running = 0_i64;
        for byte in bytes {
            if !is_ascii_whitespace(byte) {
                running += 1;
            }
            out.push(running);
        }

        out
    })
}

#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

#[pymodule]
fn omnichunk_rust(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(preprocess_nws_cumsum_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(version, module)?)?;
    Ok(())
}
