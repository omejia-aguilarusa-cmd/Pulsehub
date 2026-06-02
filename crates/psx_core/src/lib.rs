use regex::Regex;
use thiserror::Error;

#[derive(Debug, PartialEq)]
pub enum UnitSystem {
    Imperial,
    Metric,
}

#[derive(Debug, PartialEq)]
pub struct Scale {
    pub system: UnitSystem,
    /// real-world units per drawing unit
    pub factor: f64,
}

#[derive(Debug, Error, PartialEq)]
pub enum ScaleParseError {
    #[error("could not parse scale string")]
    Invalid,
}

/// Parse common architectural scale strings.
///
/// Examples accepted:
/// - `Scale: 1/8" = 1'-0"`
/// - `1:100`
/// - `1 cm = 1 m`
pub fn parse_scale(input: &str) -> Result<Scale, ScaleParseError> {
    let trimmed = input.trim();

    // Imperial pattern like 1/8" = 1'-0"
    let re_imperial = Regex::new("(?i)(\\d+(?:/\\d+)?)\\s*\"\\s*=\\s*(\\d+)'(?:-?(\\d+(?:\\.\\d+)?)\")?").unwrap();
    if let Some(caps) = re_imperial.captures(trimmed) {
        let drawing = parse_fraction(caps.get(1).unwrap().as_str())?;
        let feet: f64 = caps.get(2).unwrap().as_str().parse().unwrap();
        let inches: f64 = caps.get(3).map(|m| m.as_str().parse().unwrap()).unwrap_or(0.0);
        let real_inches = feet * 12.0 + inches;
        let factor = real_inches / drawing;
        return Ok(Scale { system: UnitSystem::Imperial, factor });
    }

    // Metric pattern like 1 cm = 1 m
    let re_metric_eq = Regex::new("(?i)1\\s*(mm|cm|m)\\s*=\\s*(\\d+(?:\\.\\d+)?)\\s*(mm|cm|m)").unwrap();
    if let Some(caps) = re_metric_eq.captures(trimmed) {
        let from_unit = caps.get(1).unwrap().as_str();
        let value: f64 = caps.get(2).unwrap().as_str().parse().unwrap();
        let to_unit = caps.get(3).unwrap().as_str();
        let from_mm = unit_to_mm(1.0, from_unit);
        let to_mm = unit_to_mm(value, to_unit);
        let factor = to_mm / from_mm;
        return Ok(Scale { system: UnitSystem::Metric, factor });
    }

    // Ratio pattern like 1:100
    let re_ratio = Regex::new("(?i)1\\s*:\\s*(\\d+(?:\\.\\d+)?)").unwrap();
    if let Some(caps) = re_ratio.captures(trimmed) {
        let factor: f64 = caps.get(1).unwrap().as_str().parse().unwrap();
        return Ok(Scale { system: UnitSystem::Metric, factor });
    }

    Err(ScaleParseError::Invalid)
}

fn parse_fraction(frac: &str) -> Result<f64, ScaleParseError> {
    if let Some((n, d)) = frac.split_once('/') {
        let n: f64 = n.parse().map_err(|_| ScaleParseError::Invalid)?;
        let d: f64 = d.parse().map_err(|_| ScaleParseError::Invalid)?;
        Ok(n / d)
    } else {
        frac.parse().map_err(|_| ScaleParseError::Invalid)
    }
}

fn unit_to_mm(value: f64, unit: &str) -> f64 {
    match unit.to_lowercase().as_str() {
        "mm" => value,
        "cm" => value * 10.0,
        "m" => value * 1000.0,
        _ => value,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_imperial_scale() {
        let s = parse_scale("Scale: 1/8\" = 1'-0\"").unwrap();
        assert_eq!(s.system, UnitSystem::Imperial);
        assert!((s.factor - 96.0).abs() < 1e-6);
    }

    #[test]
    fn parse_metric_eq_scale() {
        let s = parse_scale("1 cm = 1 m").unwrap();
        assert_eq!(s.system, UnitSystem::Metric);
        assert!((s.factor - 100.0).abs() < 1e-6);
    }

    #[test]
    fn parse_ratio_scale() {
        let s = parse_scale("1:250").unwrap();
        assert_eq!(s.system, UnitSystem::Metric);
        assert!((s.factor - 250.0).abs() < 1e-6);
    }

    #[test]
    fn invalid_scale() {
        assert!(parse_scale("foo").is_err());
    }
}
