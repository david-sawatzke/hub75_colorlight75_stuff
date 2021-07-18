use crate::hal;
use embedded_hal::blocking::serial::Write;
use litex_pac::pac;
pub use menu::Runner;
use menu::*;

pub struct Context {
    pub serial: hal::UART,
}

impl core::fmt::Write for Context {
    fn write_str(&mut self, s: &str) -> Result<(), core::fmt::Error> {
        self.serial.bwrite_all(s.as_bytes()).ok();
        Ok(())
    }
}
pub const ROOT_MENU: Menu<Context> = Menu {
    label: "root",
    items: &[&Item {
        item_type: ItemType::Callback {
            function: reboot,
            parameters: &[],
        },
        command: "reboot",
        help: Some("Reboot the soc"),
    }],
    entry: None,
    exit: None,
};

fn reboot<'a>(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    _context: &mut Context,
) {
    // Safe, because the soc is reset *now*
    unsafe { (*pac::CTRL::ptr()).reset.write(|w| w.soc_rst().set_bit()) };
}
