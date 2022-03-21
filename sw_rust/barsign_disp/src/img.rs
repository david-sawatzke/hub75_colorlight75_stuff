use core::convert::TryInto;
pub static IMG_FILE: &[u8] = include_bytes!("../../../img_data.bin");
pub static IMG_FILE_INDEXED: &[u8] = include_bytes!("../../../img_data_indexed.bin");

pub fn load_default_image() -> (
    u16,
    u32,
    impl Iterator<Item = u32>,
    impl Iterator<Item = u32>,
) {
    load_image(IMG_FILE).expect("Precompiled image should be valid")
}

pub fn load_default_indexed_image() -> (
    u16,
    u32,
    impl Iterator<Item = u32>,
    impl Iterator<Item = u32>,
    impl Iterator<Item = u32>,
) {
    load_indexed_image(IMG_FILE_INDEXED).expect("Precompiled indexed image should be valid")
}

/// Load indexed image with header & stuff
pub fn load_indexed_image(
    data: &[u8],
) -> Result<
    (
        u16,
        u32,
        impl Iterator<Item = u32> + '_,
        impl Iterator<Item = u32> + '_,
        impl Iterator<Item = u32> + '_,
    ),
    (),
> {
    let (header, data) = data.split_at(256);
    let mut header = header
        .chunks(4)
        .map(|x: &[u8]| u32::from_le_bytes(x.try_into().unwrap()));
    let header_start = header.next().unwrap();
    if header_start & (1 << 31) == 0 {
        return Err(());
    }
    let width = (header_start & 0xFFFF) as u16;
    let length = header.next().unwrap();

    let (data, colors) = data.split_at(length as usize);

    let data = data.iter().map(|x| *x as u32).take(length as usize);

    let colors = colors
        .chunks(4)
        .map(|x: &[u8]| u32::from_le_bytes(x.try_into().unwrap()));

    Ok((width, length, header.skip(2), data, colors.take(256)))
}

/// Load image with header & stuff
pub fn load_image(
    data: &[u8],
) -> Result<
    (
        u16,
        u32,
        impl Iterator<Item = u32> + '_,
        impl Iterator<Item = u32> + '_,
    ),
    (),
> {
    let (header, data) = data.split_at(256);
    let mut header = header
        .chunks(4)
        .map(|x: &[u8]| u32::from_le_bytes(x.try_into().unwrap()));
    let data = data
        .chunks(4)
        .map(|x: &[u8]| u32::from_le_bytes(x.try_into().unwrap()));
    let header_start = header.next().unwrap();
    if (header_start & (1 << 31)) != 0 {
        return Err(());
    }
    let width = (header_start & 0xFFFF) as u16;
    let length = header.next().unwrap();

    Ok((width, length, header.skip(2), data.take(length as usize)))
}

pub fn write_image(
    width: u16,
    length: u32,
    panel_params: impl Iterator<Item = u32>,
    img_data: impl Iterator<Item = u32>,
) -> Result<impl Iterator<Item = u8>, ()> {
    let header = IntoIterator::into_iter([width as u32, length, 0xD1581A40, 0xDA5A0001]);
    let iter = header
        .chain(panel_params)
        .chain(core::iter::repeat(0))
        .take(256 / 4)
        .chain(img_data.take(length as usize));

    Ok(iter
        .map(|x| IntoIterator::into_iter(x.to_le_bytes()))
        .flatten())
}

// TODO Testing doesn't currently work, due to a target without std.
// This test is just here for reference purposes right now
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn test_valid() {
        let length = 256;
        let width = 64;
        let data = [0xFF0000, 0x00FF00, 0x0000FF]
            .iter()
            .cycle()
            .take(256)
            .cloned();
        let img_data = write_image(width, length.img_data, unimplemented!(), data)
            .unwrap()
            .collect();
        assert_eq!(img_data[0], 64);
        assert_eq!(img_data[1], 0);
        assert_eq!(img_data[2], 0);
        assert_eq!(img_data[3], 0);
        assert_eq!(img_data[4], 0);
        assert_eq!(img_data[5], 1);
        assert_eq!(img_data[6], 1);
        assert_eq!(img_data[7], 0);
    }
}
