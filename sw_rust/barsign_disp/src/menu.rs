use core::fmt::Write;

use crate::hal;
use crate::hub75::{Hub75, OutputMode};
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
                function: default_indexed_image,
                parameters: &[],
            },
            command: "default_indexed_image",
            help: Some("Displays the default indexed image"),
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
                function: off,
                parameters: &[],
            },
            command: "off",
            help: Some("Turn display off"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: get_image_param,
                parameters: &[],
            },
            command: "get_image_param",
            help: Some("Get configured width & length"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: set_image_param,
                parameters: &[
                    Parameter::Mandatory {
                        parameter_name: "width",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "length",
                        help: None,
                    },
                ],
            },
            command: "set_image_param",
            help: Some("Set width & length"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: get_panel_param,
                parameters: &[
                    Parameter::Mandatory {
                        parameter_name: "output",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "chain_num",
                        help: None,
                    },
                ],
            },
            command: "get_panel_param",
            help: Some("Get virtual location of panel in 32 increments"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: set_panel_param,
                parameters: &[
                    Parameter::Mandatory {
                        parameter_name: "output",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "chain_num",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "x",
                        help: None,
                    },
                    Parameter::Mandatory {
                        parameter_name: "y",
                        help: None,
                    },
                ],
            },
            command: "set_panel_param",
            help: Some("Set virtual location of panel in 32 increments"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: set_default_panel_params,
                parameters: &[],
            },
            command: "set_default_panel_params",
            help: Some("Sets the default panel parameters"),
        },
        &Item {
            item_type: ItemType::Callback {
                function: check_flash,
                parameters: &[],
            },
            command: "check_flash",
            help: Some("Check if reading the flash work as expected"),
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
    let img_data = crate::img::write_image(
        width,
        length,
        hub75.get_panel_params(),
        hub75.read_img_data(),
    )
    .unwrap();
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
    hub75.write_img_data(0, image.3);
    hub75.set_mode(OutputMode::FullColor);
    hub75.on();
}

fn default_indexed_image(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    use crate::img;
    let hub75 = &mut context.hub75;
    writeln!(context.serial, "Start load");
    let image = img::load_default_indexed_image();
    writeln!(context.serial, "loading");
    hub75.set_img_param(image.0, image.1);
    writeln!(context.serial, "data");
    hub75.write_img_data(0, image.3);
    writeln!(context.serial, "mode");
    hub75.set_mode(OutputMode::Indexed);
    writeln!(context.serial, "palette");
    hub75.set_palette(0, image.4);
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
    hub75.set_panel_params(image.2);
    hub75.write_img_data(0, image.3);
    // TODO indexed
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
    let img_data = img::write_image(
        width,
        length,
        hub75.get_panel_params(),
        hub75.read_img_data(),
    )
    .unwrap();
    context.flash.write_image(img_data);
}

fn on(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.on();
}

fn off(_menu: &Menu<Context>, _item: &Item<Context>, _args: &[&str], context: &mut Context) {
    context.hub75.off();
}

fn get_image_param(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    let (width, length) = context.hub75.get_img_param();
    writeln!(context, r#"{{"width": {}, "length": {}}}"#, width, length).unwrap();
}

fn set_image_param(
    _menu: &Menu<Context>,
    item: &Item<Context>,
    args: &[&str],
    context: &mut Context,
) {
    let width: Result<u16, _> = argument_finder(item, args, "width")
        .unwrap()
        .unwrap()
        .parse();
    let length: Result<u32, _> = argument_finder(item, args, "length")
        .unwrap()
        .unwrap()
        .parse();
    if width.is_err() || length.is_err() {
        writeln!(context, "Invalid number given").unwrap();
        return;
    }
    context.hub75.set_img_param(width.unwrap(), length.unwrap());
}
fn get_panel_param(
    _menu: &Menu<Context>,
    item: &Item<Context>,
    args: &[&str],
    context: &mut Context,
) {
    let output: Result<u8, _> = argument_finder(item, args, "output")
        .unwrap()
        .unwrap()
        .parse();
    let chain_num: Result<u8, _> = argument_finder(item, args, "chain_num")
        .unwrap()
        .unwrap()
        .parse();
    if output.is_err() || chain_num.is_err() {
        writeln!(context, "Invalid number given").unwrap();
        return;
    }
    let (x, y) = context
        .hub75
        .get_panel_param(output.unwrap(), chain_num.unwrap());
    writeln!(context, r#"{{"x": {}, "y": {}}}"#, x, y).unwrap();
}
fn set_panel_param(
    _menu: &Menu<Context>,
    item: &Item<Context>,
    args: &[&str],
    context: &mut Context,
) {
    let output: Result<u8, _> = argument_finder(item, args, "output")
        .unwrap()
        .unwrap()
        .parse();
    let chain_num: Result<u8, _> = argument_finder(item, args, "chain_num")
        .unwrap()
        .unwrap()
        .parse();
    let x: Result<u8, _> = argument_finder(item, args, "x").unwrap().unwrap().parse();
    let y: Result<u8, _> = argument_finder(item, args, "y").unwrap().unwrap().parse();
    if output.is_err() || chain_num.is_err() || x.is_err() || y.is_err() {
        writeln!(context, "Invalid number given").unwrap();
        return;
    }
    context
        .hub75
        .set_panel_param(output.unwrap(), chain_num.unwrap(), x.unwrap(), y.unwrap());
}

fn set_default_panel_params(
    _menu: &Menu<Context>,
    _item: &Item<Context>,
    _args: &[&str],
    context: &mut Context,
) {
    context.hub75.set_panel_param(0, 0, 0, 0);
    context.hub75.set_panel_param(0, 1, 0, 1);
    context.hub75.set_panel_param(0, 2, 2, 0);
    context.hub75.set_panel_param(0, 3, 2, 1);
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
