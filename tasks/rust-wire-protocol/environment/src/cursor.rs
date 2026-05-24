/// Read cursor over a byte buffer with bounds-checked access methods.
pub struct Cursor<'a> {
    buf: &'a [u8],
    pos: usize,
    limit: usize,
}

impl<'a> Cursor<'a> {
    pub fn new(buf: &'a [u8]) -> Self {
        Self {
            buf,
            pos: 0,
            limit: buf.len(),
        }
    }

    pub fn with_limit(buf: &'a [u8], limit: usize) -> Self {
        Self {
            buf,
            pos: 0,
            limit: limit.min(buf.len()),
        }
    }

    pub fn pos(&self) -> usize {
        self.pos
    }

    pub fn remaining(&self) -> usize {
        if self.pos >= self.limit {
            0
        } else {
            self.limit - self.pos
        }
    }

    pub fn advance(&mut self, n: usize) -> bool {
        if self.pos + n <= self.limit {
            self.pos += n;
            true
        } else {
            false
        }
    }

    pub fn peek_u8(&self) -> Option<u8> {
        if self.pos < self.limit {
            Some(self.buf[self.pos])
        } else {
            None
        }
    }

    pub fn read_u8(&mut self) -> Option<u8> {
        if self.pos < self.limit {
            let v = self.buf[self.pos];
            self.pos += 1;
            Some(v)
        } else {
            None
        }
    }

    pub fn read_u16_le(&mut self) -> Option<u16> {
        if self.pos + 2 <= self.limit {
            let v = u16::from_le_bytes([self.buf[self.pos], self.buf[self.pos + 1]]);
            self.pos += 2;
            Some(v)
        } else {
            None
        }
    }

    pub fn read_u32_le(&mut self) -> Option<u32> {
        if self.pos + 4 <= self.limit {
            let v = u32::from_le_bytes([
                self.buf[self.pos],
                self.buf[self.pos + 1],
                self.buf[self.pos + 2],
                self.buf[self.pos + 3],
            ]);
            self.pos += 4;
            Some(v)
        } else {
            None
        }
    }

    pub fn read_i32_le(&mut self) -> Option<i32> {
        if self.pos + 4 <= self.limit {
            let v = i32::from_le_bytes([
                self.buf[self.pos],
                self.buf[self.pos + 1],
                self.buf[self.pos + 2],
                self.buf[self.pos + 3],
            ]);
            self.pos += 4;
            Some(v)
        } else {
            None
        }
    }

    pub fn read_u64_le(&mut self) -> Option<u64> {
        if self.pos + 8 <= self.limit {
            let v = u64::from_le_bytes([
                self.buf[self.pos],
                self.buf[self.pos + 1],
                self.buf[self.pos + 2],
                self.buf[self.pos + 3],
                self.buf[self.pos + 4],
                self.buf[self.pos + 5],
                self.buf[self.pos + 6],
                self.buf[self.pos + 7],
            ]);
            self.pos += 8;
            Some(v)
        } else {
            None
        }
    }

    pub fn read_i64_le(&mut self) -> Option<i64> {
        if self.pos + 8 <= self.limit {
            let v = i64::from_le_bytes([
                self.buf[self.pos],
                self.buf[self.pos + 1],
                self.buf[self.pos + 2],
                self.buf[self.pos + 3],
                self.buf[self.pos + 4],
                self.buf[self.pos + 5],
                self.buf[self.pos + 6],
                self.buf[self.pos + 7],
            ]);
            self.pos += 8;
            Some(v)
        } else {
            None
        }
    }

    pub fn read_slice(&mut self, len: usize) -> Option<&'a [u8]> {
        if self.pos + len <= self.limit {
            let s = &self.buf[self.pos..self.pos + len];
            self.pos += len;
            Some(s)
        } else {
            None
        }
    }

    pub fn set_pos(&mut self, pos: usize) {
        self.pos = pos;
    }
}
