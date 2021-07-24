// TODO Add palette
use litex_pac as pac;

static CHAIN_LENGTH: u8 = 4;

pub struct Hub75 {
    hub75: pac::HUB75,
    hub75_data: &'static mut [u32],
    _hub75_palette: pac::HUB75_PALETTE,
    length: u32,
}

impl Hub75 {
    pub fn new(hub75: pac::HUB75, hub75_palette: pac::HUB75_PALETTE) -> Self {
        let hub75_data = unsafe {
            core::slice::from_raw_parts_mut(
                (0x40000000 + 0x00400000 / 2) as *mut u32,
                0x00400000 / 2 / 4,
            )
        };

        Self {
            hub75,
            hub75_data,
            _hub75_palette: hub75_palette,
            length: 0,
        }
    }
    pub fn on(&mut self) {
        self.hub75.ctrl.modify(|_, w| w.enabled().set_bit());
    }
    pub fn off(&mut self) {
        self.hub75.ctrl.modify(|_, w| w.enabled().clear_bit());
    }
    pub fn write_img_data(&mut self, offset: usize, data: impl Iterator<Item = u32>) {
        let sdram = self.hub75_data[offset..].iter_mut();
        for (sdram, data) in sdram.zip(data) {
            *sdram = data;
        }
        // TODO flush cache
    }

    pub fn read_img_data<'a>(&'a self) -> impl Iterator<Item = &'a u32> {
        self.hub75_data[0..self.length as usize].iter()
    }

    pub fn set_img_param(&mut self, width: u16, length: u32) {
        unsafe { self.hub75.ctrl.write(|w| w.width().bits(width)) };
        self.length = length;
    }

    pub fn get_img_param(&self) -> (u16, u32) {
        let width = self.hub75.ctrl.read().width().bits();
        (width, self.length)
    }

    pub fn set_panel_param(&mut self, output: u8, chain_num: u8, x: u8, y: u8) {
        use pac::hub75::PANEL0_0;
        let chain_offset = (output * CHAIN_LENGTH + chain_num) as usize;
        let panel_adr = &self.hub75.panel0_0 as *const PANEL0_0;
        let panel_reg: &[PANEL0_0] =
            unsafe { core::slice::from_raw_parts(panel_adr, (8 * CHAIN_LENGTH) as usize) };
        unsafe { panel_reg[chain_offset].write(|w| w.x().bits(x).y().bits(y)) };
    }

    pub fn get_panel_param(&mut self, output: u8, chain_num: u8) -> (u8, u8) {
        use pac::hub75::PANEL0_0;
        let chain_offset = (output * CHAIN_LENGTH + chain_num) as usize;
        let panel_adr = &self.hub75.panel0_0 as *const PANEL0_0;
        let panel_reg: &[PANEL0_0] =
            unsafe { core::slice::from_raw_parts(panel_adr, (8 * CHAIN_LENGTH) as usize) };
        let data = panel_reg[chain_offset].read();
        (data.x().bits(), data.y().bits())
    }
}
