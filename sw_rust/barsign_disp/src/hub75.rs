use litex_pac as pac;

const CHAIN_LENGTH: u8 = 4;
const OUTPUTS: u8 = 8;

pub struct Hub75 {
    hub75: pac::HUB75,
    hub75_data: &'static mut [u32],
    hub75_palette: pac::HUB75_PALETTE,
    length: u32,
}

pub enum OutputMode {
    FullColor,
    Indexed,
}

impl Hub75 {
    pub fn new(hub75: pac::HUB75, hub75_palette: pac::HUB75_PALETTE) -> Self {
        let hub75_data = unsafe {
            core::slice::from_raw_parts_mut(
                (0x90000000u32 + 0x00400000 / 2) as *mut u32,
                0x00400000 / 2 / 4,
            )
        };

        Self {
            hub75,
            hub75_data,
            hub75_palette,
            length: 0,
        }
    }

    pub fn on(&mut self) {
        self.hub75.ctrl.modify(|_, w| w.enabled().set_bit());
    }

    pub fn off(&mut self) {
        self.hub75.ctrl.modify(|_, w| w.enabled().clear_bit());
    }

    pub fn set_mode(&mut self, mode: OutputMode) {
        self.hub75.ctrl.modify(|_, w| match mode {
            OutputMode::FullColor => w.indexed().clear_bit(),
            OutputMode::Indexed => w.indexed().set_bit(),
        });
    }

    pub fn get_mode(&mut self) -> OutputMode {
        match self.hub75.ctrl.read().indexed().bit() {
            false => OutputMode::FullColor,
            true => OutputMode::Indexed,
        }
    }

    pub fn write_img_data(&mut self, offset: usize, data: impl Iterator<Item = u32>) {
        let sdram = self.hub75_data[offset..].iter_mut();
        for (count, (sdram, data)) in sdram
            .zip(data)
            .take(self.length as usize - offset)
            .enumerate()
        {
            *sdram = data;
        }
    }

    pub fn read_img_data<'a>(&'a self) -> impl Iterator<Item = u32> + 'a {
        self.hub75_data[0..self.length as usize].iter().copied()
    }

    pub fn set_img_param(&mut self, width: u16, length: u32) {
        unsafe { self.hub75.ctrl.modify(|_, w| w.width().bits(width)) };
        self.length = length;
    }

    pub fn get_img_param(&self) -> (u16, u32) {
        let width = self.hub75.ctrl.read().width().bits();
        (width, self.length)
    }

    pub fn get_panel_params<'a>(&'a self) -> impl Iterator<Item = u32> + 'a {
        use pac::hub75::PANEL0_0;
        let panel_adr = &self.hub75.panel0_0 as *const PANEL0_0 as *const u32;
        let panel_reg: &[u32] =
            unsafe { core::slice::from_raw_parts(panel_adr, (OUTPUTS * CHAIN_LENGTH) as usize) };
        panel_reg.iter().copied()
    }

    pub fn set_panel_params(&mut self, params: impl Iterator<Item = u32>) {
        use pac::hub75::PANEL0_0;
        let panel_adr = &self.hub75.panel0_0 as *const PANEL0_0;
        let panel_reg: &[PANEL0_0] =
            unsafe { core::slice::from_raw_parts(panel_adr, (OUTPUTS * CHAIN_LENGTH) as usize) };
        for (reg, data) in panel_reg.iter().zip(params) {
            unsafe { reg.write(|w| w.bits(data)) };
        }
    }

    pub fn set_panel_param(&mut self, output: u8, chain_num: u8, x: u8, y: u8) {
        if output >= OUTPUTS || chain_num >= CHAIN_LENGTH {
            return;
        }
        use pac::hub75::PANEL0_0;
        let chain_offset = (output * CHAIN_LENGTH + chain_num) as usize;
        let panel_adr = &self.hub75.panel0_0 as *const PANEL0_0;
        let panel_reg: &[PANEL0_0] =
            unsafe { core::slice::from_raw_parts(panel_adr, (OUTPUTS * CHAIN_LENGTH) as usize) };
        unsafe { panel_reg[chain_offset].write(|w| w.x().bits(x).y().bits(y)) };
    }

    pub fn get_panel_param(&mut self, output: u8, chain_num: u8) -> (u8, u8) {
        if output >= OUTPUTS || chain_num >= CHAIN_LENGTH {
            return (255, 255);
        }
        use pac::hub75::PANEL0_0;
        let chain_offset = (output * CHAIN_LENGTH + chain_num) as usize;
        let panel_adr = &self.hub75.panel0_0 as *const PANEL0_0;
        let panel_reg: &[PANEL0_0] =
            unsafe { core::slice::from_raw_parts(panel_adr, (OUTPUTS * CHAIN_LENGTH) as usize) };
        let data = panel_reg[chain_offset].read();
        (data.x().bits(), data.y().bits())
    }

    pub fn set_palette(&mut self, offset: u8, data: impl Iterator<Item = u32>) {
        const LENGTH: usize = 256;
        use pac::hub75_palette::HUB75_PALETTE;
        let palette_adr = &self.hub75_palette.hub75_palette as *const HUB75_PALETTE;
        let palette_data: &[HUB75_PALETTE] =
            unsafe { core::slice::from_raw_parts(palette_adr, LENGTH) };
        for (index, data) in data.take(LENGTH - (offset as usize)).enumerate() {
            unsafe { palette_data[index + (offset as usize)].write(|w| w.bits(data)) };
        }
    }

    pub fn get_palette(&mut self) -> &'_ [u32] {
        const LENGTH: usize = 256;
        use pac::hub75_palette::HUB75_PALETTE;
        let palette_adr = &self.hub75_palette.hub75_palette as *const HUB75_PALETTE as *const u32;
        let palette_data: &[u32] = unsafe { core::slice::from_raw_parts(palette_adr, LENGTH) };
        palette_data
    }
}
