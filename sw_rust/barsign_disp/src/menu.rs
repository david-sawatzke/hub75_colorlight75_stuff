use core::fmt::Write;

use crate::hal;
use crate::hub75::Hub75;
use crate::img_flash::Flash;
use embedded_hal::prelude::_embedded_hal_blocking_serial_Write;
use litex_pac::pac;
pub use menu::Runner;
use menu::*;

pub struct Context {
    pub serial: hal::UART,
    pub hub75: Hub75,
    pub flash: Flash,
}

impl core::fmt::Write for Context {
    fn write_str(&mut self, s: &str) -> Result<(), core::fmt::Error> {
        use embedded_hal::blocking::serial::Write;
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
                function: default_image,
                parameters: &[],
            },
            command: "default_image",
            help: Some("Displays the default image"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: load_spi_image,
                parameters: &[],
            },
            command: "load_spi_image",
            help: Some("Displays the spi image"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: save_spi_image,
                parameters: &[],
            },
            command: "save_spi_image",
            help: Some("Saves the current image in spi flash"),
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
                function: check_flash,
                parameters: &[],
            },
            command: "check_flash",
            help: Some("Check if reading the flash work as expected"),
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
    let (width, length) = hub75.get_img_param();
    let img_data = crate::img::write_image(width, length, hub75.read_img_data()).unwrap();
    let mut size = 0;
    for (byte_count, data) in img_data.enumerate() {
        if crate::img::IMG_FILE[byte_count] != data {
            write!(
                context.serial,
                "Addr 0x{:x} and content 0x{:x} don't match\n",
                byte_count, data
            )
            .unwrap();
        }
        size = byte_count + 1;
    }
    write!(context.serial, "Size 0x{:x}", size).unwrap();
    hub75.set_img_param(128, 128 * 128);
    let data = [0xFF0000, 0x00FF00, 0x0000FF];
    hub75.write_img_data(0, data.iter().cycle().take(128).map(|x| *x));
    hub75.on();
}

fn default_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    let image = img::load_default_image();
    hub75.set_img_param(image.0, image.1);
    hub75.write_img_data(0, image.2);
    hub75.on();
}

fn load_spi_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    let image = img::load_image(context.flash.read_image()).unwrap();
    hub75.set_img_param(image.0, image.1);
    hub75.write_img_data(0, image.2);
    hub75.on();
}

fn save_spi_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    let (width, length) = hub75.get_img_param();
    let img_data = img::write_image(width, length, hub75.read_img_data()).unwrap();
    context.flash.write_image(img_data);
}

fn on(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.on();
}

fn off(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.off();
}

fn check_flash(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    if context.flash.memory_read_test() == true {
        context.write_str("Flash reading seems to work!").unwrap();
    } else {
        context.write_str("Flash reading doesn't work!").unwrap();
    }
}
