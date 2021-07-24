use crate::hal;
use crate::hub75;
use crate::hub75::Hub75;
use embedded_hal::blocking::serial::Write;
use litex_pac::pac;
pub use menu::Runner;
use menu::*;

pub struct Context {
    pub serial: hal::UART,
    pub hub75: Hub75,
}

impl core::fmt::Write for Context {
    fn write_str(&mut self, s: &str) -> Result<(), core::fmt::Error> {
        self.serial.bwrite_all(s.as_bytes()).ok();
        Ok(())
    }
}
pub const ROOT_MENU: Menu<Context> = Menu {
    label: "root",
    items: &[
        &Item {
            item_type: ItemType::Callback {
                function: reboot,
                parameters: &[],
            },
            command: "reboot",
            help: Some("Reboot the soc"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: out_test,
                parameters: &[],
            },
            command: "out_test",
            help: Some("Displays a pattern on screen"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: on,
                parameters: &[],
            },
            command: "on",
            help: Some("Turn display off"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: off,
                parameters: &[],
            },
            command: "off",
            help: Some("Turn display off"),
        },
    ],
    entry: None,
    exit: None,
};

fn reboot(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], _context: &mut Context) {
    // Safe, because the soc is reset *now*
    unsafe { (*pac::CTRL::ptr()).reset.write(|w| w.soc_rst().set_bit()) };
}

fn out_test(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    let hub75 = &mut context.hub75;
    hub75.set_img_param(128, 128 * 128);
    let data = [0xFF0000, 0x00FF00, 0x0000FF];
    hub75.write_img_data(0, data.iter().cycle().take(128).map(|x| *x));
    hub75.on();
}

fn on(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.on();
}

fn off(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.off();
}
