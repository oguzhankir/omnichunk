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
fn build_char_to_byte_index(py: Python<'_>, data: &[u8]) -> (Vec<u32>, Vec<u32>) {
    let bytes = data.to_vec();
    py.allow_threads(move || {
        let char_count = bytecount_chars(&bytes);
        let mut char_to_byte: Vec<u32> = Vec::with_capacity(char_count + 1);
        let mut line_starts: Vec<u32> = vec![0];

        let mut byte_pos: u32 = 0;
        let mut char_idx: u32 = 0;
        let mut i = 0;

        while i < bytes.len() {
            char_to_byte.push(byte_pos);
            let b = bytes[i];
            let char_len = if b < 0x80 {
                1
            } else if b < 0xE0 {
                2
            } else if b < 0xF0 {
                3
            } else {
                4
            };
            if b == b'\n' {
                line_starts.push(char_idx + 1);
            }
            byte_pos += char_len as u32;
            char_idx += 1;
            i += char_len;
        }
        char_to_byte.push(byte_pos);

        (char_to_byte, line_starts)
    })
}

#[inline]
fn bytecount_chars(bytes: &[u8]) -> usize {
    bytes.iter().filter(|&&b| (b & 0xC0) != 0x80).count()
}

#[pyfunction]
fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// Adjacent cosine similarities: output[i] = cosine(embeddings[i], embeddings[i+1])
/// `embeddings` is a flat f32 row-major buffer of shape (N, D); `dim` is D.
#[pyfunction]
fn batch_cosine_similarity_adjacent(embeddings: Vec<f32>, dim: usize) -> PyResult<Vec<f32>> {
    if dim == 0 {
        return Err(pyo3::exceptions::PyValueError::new_err("dim must be > 0"));
    }
    if embeddings.len() % dim != 0 {
        return Err(pyo3::exceptions::PyValueError::new_err(
            "embeddings length must be divisible by dim",
        ));
    }
    let n = embeddings.len() / dim;
    if n == 0 {
        return Ok(vec![]);
    }
    let data = embeddings;
    let mut out = Vec::with_capacity(n.saturating_sub(1));
    for i in 0..n.saturating_sub(1) {
        let a = &data[i * dim..(i + 1) * dim];
        let b = &data[(i + 1) * dim..(i + 2) * dim];
        let dot: f32 = a.iter().zip(b.iter()).map(|(x, y)| x * y).sum();
        let na: f32 = a.iter().map(|x| x * x).sum::<f32>().sqrt();
        let nb: f32 = b.iter().map(|x| x * x).sum::<f32>().sqrt();
        let denom = na * nb;
        out.push(if denom > 0.0 { dot / denom } else { 0.0 });
    }
    Ok(out)
}

#[pymodule]
fn omnichunk_rust(_py: Python<'_>, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(preprocess_nws_cumsum_bytes, module)?)?;
    module.add_function(wrap_pyfunction!(build_char_to_byte_index, module)?)?;
    module.add_function(wrap_pyfunction!(version, module)?)?;
    module.add_function(wrap_pyfunction!(batch_cosine_similarity_adjacent, module)?)?;
    Ok(())
}
