#![no_std]

// Generated file, ignore warnings and formatting
#[allow(non_camel_case_types, clippy::all)]
#[rustfmt::skip]
pub mod pac;

pub use pac::generic::*;
pub use pac::*;
pub use riscv;
#[cfg(feature = "rt")]
pub use riscv_rt;
