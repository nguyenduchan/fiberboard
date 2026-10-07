# Fiberboard

Fiberboard là bo mạch điều khiển **logic tích hợp (AIO)**, không có driver stepper Nema. Dùng cho bơm DC, cấp liệu feeder, báo vật thể lạ và mini filler.

Trên bo có **đế cắm ESP32-DevKitC** (nạp phần mềm nhúng qua USB trên module). Nguồn vào **9–24 VDC**. Hai kênh quang **sợi POF 1 mm** (AFBR) gắn trên PCB. Đầu ra relay và van solenoid, **RS485**. Mỗi giắc vào/ra có **đèn SMD 0805** sát cọc. Trong cột nguồn có đèn debug: **D27** sáng khi +24 V sau bảo vệ còn điện, **D25** khi buck ra +5 V, **D6** khi LDO ra 3,3 V. Không có header OLED trên bo.

Kho mã này chỉ chứa thiết kế KiCad và script sinh mạch/layout. **Phần mềm nhúng (firmware)** không có trong kho.

Ghi chú thiết kế chi tiết: [`pcb/DESIGN_NOTES.txt`](pcb/DESIGN_NOTES.txt)

Khối **bảo vệ 24 V + buck** (dùng chung nhiều loại bo): [`pcb/PWR_24V_PROTECT_BUCK_GUIDE.txt`](pcb/PWR_24V_PROTECT_BUCK_GUIDE.txt)

---

## Chức năng các khối

| Khối | Mô tả |
|------|--------|
| **MCU** | ESP32-DevKitC trên đế cắm; nạp firmware qua USB trên module |
| **Nguồn** | VIN → **F1/L2/RV1/D7/Q12/C4** → **XL1509** → **+5V**. Mỗi relay lấy +5 V qua ferrite riêng (FB4 / FB5). **AMS1117** → 3,3 V. Chỉ **một** cầu chì F1 tại nguồn tổng 24 V. Mass **NT1+D11+C23+FB3**. Chi tiết: [`pcb/PWR_24V_PROTECT_BUCK_GUIDE.txt`](pcb/PWR_24V_PROTECT_BUCK_GUIDE.txt) |
| **Quang 2 kênh** | Phát AFBR-1624Z + thu AFBR-2624Z mỗi kênh; sợi POF 1 mm cắm trên bo |
| **Đầu vào số** | FOOT (công tắc chân), NPN (cảm biến); cách ly quang PC817 |
| **Đầu ra** | 2 relay G6KU (COM/NO/NC) + 1 van solenoid (MOSFET 24 V); domino J5/J6/J7 (**2EDG5.08**, bước 5,08 mm); flyback D3/D4 (cuộn relay 5 V), D5 SS34 (solenoid trên J7); driver 2N3904 + AO3400A. Tiếp điểm relay kín — tải cảm lớn: snubber/diode tại tải hoặc theo catalog relay |
| **Giao tiếp** | RS485 bán song công (MAX485); **TVS D9/D10** + **R18/R19** trên A/B; LED trạng thái; I2C chỉ trên ESP32 |

Bảo vệ trên bo (tóm tắt): **F1** = một giá cầu chì **5×20 mm** tại nguồn tổng 24 V (ống thủy tinh thay bằng tay, không PPTC SMD); **L2, RV1, D7, C4**; mass **NT1, D11, C23, FB3**; relay **D12/C24**; van lấy **+24V** sau F1. Đầu vào quang PC817; RS485 **D9/D10**. Lắp tủ: nguồn 24 V ≥ 1,5–2 A, dây xoắn, IEC 61000-6-2; dừng khẩn / SIL — phần cứng an toàn riêng.

---

## Đầu nối ra ngoài (I/O)

**Cạnh dài trên** (trái → phải): `J1 | J3 | J4 | F1T | F1R | F2T | F2R` — nguồn vào 24 V, chân, NPN, quang.

**Cạnh dài dưới** (trái → phải): `J5 | J6 | J7 | J2 | J8` — relay 1, relay 2, van, giắc 24 V ra cho bàn phím, rồi RS485. Các giắc giãn trên suốt cạnh; cột relay, van và RS485 rộng hơn để xếp linh kiện trong khung của cọc. Cột trái trong lòng là bảo vệ 24 V, cột kế là buck.

| Ref | Tên | Chân | Ý nghĩa |
|-----|-----|------|---------|
| **J1** | VIN | 1 | +9 … +24 VDC |
| | | 2 | Mass domino nguồn |
| **F1T** | Quang 1 phát | POF | Phát; cắm sợi 1 mm thẳng vào mắt hướng ra cạnh bo |
| **F1R** | Quang 1 thu | POF | Thu kênh 1 (cùng chiều cắm như phát) |
| **F2T** | Quang 2 phát | POF | Phát kênh 2 |
| **F2R** | Quang 2 thu | POF | Thu kênh 2 |
| **J3** | FOOT | 1 | Cực A công tắc chân (qua opto) |
| | | 2 | Cực K / mass về |
| **J4** | NPN | 1 | V+ 24 V cho cảm biến hiện trường |
| | | 2 | SIG (tín hiệu NPN) |
| | | 3 | Mass hiện trường (GND_PWR) |
| **J5** | RELAY 1 | 1 / 2 / 3 | COM / NO / NC |
| **J6** | RELAY 2 | 1 / 2 / 3 | COM / NO / NC |
| **J7** | SOLENOID | 1 | +24 V (cực dương cuộn van) |
| | | 2 | SOL− (cực âm; bo cắt mass phía âm) |
| **J2** | Keyboard | 1 / 2 | +24 V đã qua F1 (cùng rail +24V) / mass nguồn. Cấp cho J_PWR mạch keyboard |
| **J8** | RS485 | 1 / 2 / 3 | A / B / mass logic (**2EDG5.08-3P** cái trên bo) |

### Domino hiện trường — **2EDG5.08** (dễ mua Shopee)

| Hạng mục | Khuyến nghị |
|----------|-------------|
| **Trên PCB** | Socket **2EDG5.08** cái, chân ngang 5,08 mm (footprint `Fiberboard:Terminal_2EDG5.08-…`) |
| **Dây ra hiện trường** | **Đầu đực 2EDG** cùng bước (bộ **đực + cái** 2P/3P), siết dây vào đực; hoặc cáp **CH5.08** một đầu + đầu đực 2EDG tùy shop |
| **Tìm mua** | Shopee: `2EDG5.08 3P đực cái thẳng` · `2EDG5.08 2P` · `cáp CH5.08 3P 20cm` (đầu jack — thường gắn thêm đực 2EDG nếu cần) |

### RS485 (J8)

| Hạng mục | Khuyến nghị |
|----------|-------------|
| **Cắm** | **2EDG5.08-3P** đực (giống J4–J6) |
| **Cáp** | Đôi xoắn **2×0,25–0,5 mm²** + bọc chắn; **A/B** chân 1–2, **mass** chân 3; bọc chắn nối mass **một đầu** |
| **Trên bo** | **R15 100 Ω** giữa A–B (điểm cuối bus — termination; gộp mã với R13) |
| **Bố trí** | **J8** ở **cạnh dài dưới** (cùng hàng relay/van), góc phải |

| Ref | Socket trên bo | Dây hiện trường (phổ biến VN) |
|-----|----------------|-------------------------------|
| **J1, J3, J7** | 2EDG **2P** cái | Đực **2EDG5.08-2P** + dây 0,5–1,5 mm² |
| **J4, J5, J6, J8** | 2EDG **3P** cái | Đực **2EDG5.08-3P** (+ cáp xoắn có bọc cho RS485) |

Cột I/O tính theo **bề ngang cắm đực 2EDG**, xếp trên **cạnh dài** của hộp 145×90×40.

---

## GPIO ESP32 (tham chiếu firmware)

Tên tín hiệu trong firmware giữ nguyên; cột **Hướng** = vào/ra MCU.

| GPIO | Tín hiệu | Hướng | Ghi chú |
|------|-----------|-------|---------|
| IO32 | FIBER1_PWM | Ra | LEDC PWM → phát quang kênh 1 |
| IO33 | FIBER2_PWM | Ra | LEDC PWM → phát quang kênh 2 |
| IO4 | FIBER1_DIG | Vào | TTL từ thu quang kênh 1 |
| IO15 | FIBER2_DIG | Vào | TTL từ thu quang kênh 2 |
| IO25 | IN_FOOT | Vào | Công tắc chân (sau opto) |
| IO26 | IN_NPN | Vào | Cảm biến NPN (sau opto) |
| IO27 | OUT_RLY1 | Ra | Driver relay 1 |
| IO14 | OUT_RLY2 | Ra | Driver relay 2 |
| IO13 | OUT_MOS | Ra | Solenoid |
| IO16 | RS485_RX | Vào | UART RX (MAX485) |
| IO17 | RS485_DE | Ra | DE và RE# (MAX485) |
| IO23 | RS485_TX | Ra | UART TX |
| IO21 | I2C_SDA | Hai chiều | Không ra header bo (tùy chọn ngoài) |
| IO22 | I2C_SCL | Ra | Không ra header bo (tùy chọn ngoài) |

IO32, IO33, IO4, IO15, IO23 và IO16 có điện trở nối tiếp 1 kΩ (R40–R45) trước mắt quang và MAX485.

---

## Thư mục trong kho mã

| Đường dẫn | Vai trò |
|-----------|---------|
| `pcb/fiberboard-logic.kicad_pro` | Dự án KiCad 10 (sơ đồ + PCB) |
| `pcb/DESIGN_NOTES.txt` | Ghi chú nguồn, layout, quang |
| `pcb/PWR_24V_PROTECT_BUCK_GUIDE.txt` | Hướng dẫn khối bảo vệ 24 V và buck (dùng chung) |
| `pcb/BOM.txt` | BOM đầy đủ + bảng **gộp mã** linh kiện cơ bản + giá VND |
| `pcb/ASSEMBLY.txt` | Vùng lắp ráp tùy chọn theo giắc (DNP cả nhóm) |
| `pcb/libraries/` | Symbol và footprint Fiberboard |
| `pcb/scripts/generate_kicad_project.py` | Sinh lại sơ đồ/PCB/thư viện |
| `pcb/scripts/connectivity.py` | Danh sách mạng và kết nối |
| `pcb/scripts/pcb_layout.py` | Vị trí footprint, silk I/O |
| `pcb/scripts/check_*.py` | Kiểm ERC, netlist, chân (hỗ trợ) |

---

## Cách làm việc

| Bước | Việc cần làm |
|------|----------------|
| 1 | Mở `pcb/fiberboard-logic.kicad_pro` trong KiCad 10 |
| 2 | Sau khi sửa Python: `python pcb/scripts/generate_kicad_project.py` (cần KiCad 10; đường dẫn KiCad trong script) |
| 3 | Đi dây PCB theo ratsnest; refill pour **GND** và **GND_PWR** tại điểm sao **NT1** (cạnh C4) |
| 3b | Sau `generate_kicad_project.py`: `python pcb/scripts/check_pcb_layout.py` — kiểm tra chồng linh kiện. **DRC đỏ “unconnected”** là bình thường khi chưa đi dây (file sinh ra không có track) |

---

## Kích thước bo và vỏ

> **Vỏ:** hộp PLC **145 × 90 × 40 mm** (mã 145T-1D). Giắc nhà máy nằm trên **cạnh dài** (~20 vị trí, pitch 5 mm), không phải hai đầu 90 mm. Lòng thân khoảng **125 × 90 mm**. PCB **118 × 84 mm**.

| Hạng mục | Giá trị |
|----------|---------|
| **PCB** | 118 × 84 mm |
| **Vỏ** | Hộp PLC ABS 145 × 90 × 40 mm |
| **Giắc** | Cạnh dài trên: J1 nguồn vào, J3 chân, J4 NPN, quang. Cạnh dài dưới: J5/J6 relay, J7 van sát J2 (24 V ra bàn phím), J8 RS485 |
| **Lớp / độ dày** | 2 lớp FR4, 1,6 mm |
| **Lắp ráp** | SMD ưu tiên; domino và AFBR xuyên lỗ theo footprint |
| **Silk mép dưới** | Cột I/O: nhãn tiếng Việt sát giắc cắm, căn giữa ô; chỉnh trong `pcb/scripts/pcb_layout.py` → `IO_LABELS` |

### Ước giá linh kiện (tham chiếu)

Chi tiết từng mã: [`pcb/BOM.txt`](pcb/BOM.txt). Tóm tắt (lẻ VN, 1 bo):

| Hạng mục | Khoảng (k VND) |
|----------|----------------|
| Linh kiện trên PCB (không gồm module ESP32) | ~530 – 1.060 |
| ESP32-DevKitC | ~90 – 185 |
| PCB 2 lớp 118×84 mm | ~25 – 120 |
| **Lắp đủ một máy** | **~645 – 1.365** |

Khối nguồn + cầu chì 5×20: ~165–300k (không relay). Quang AFBR và relay là hai khoản biến động lớn nhất.
