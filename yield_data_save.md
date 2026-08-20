# Сохранение данных урожайности (Yield)

## Обзор

Данные урожайности формируются из PGN 243 (Yield Data In) от yield-модуля, обрабатываются классом `Yield` (`backend/yield.cpp`) и сохраняются в файл `YieldData.txt` в папке поля.

## Путь сохранения

```
<Documents>/QtAgOpenGPS/Fields/<fieldDir>/YieldData.txt
```

- На десктопе: `QStandardPaths::DocumentsLocation` + `/QtAgOpenGPS/Fields/<fieldDir>/`
- На Android: `/storage/emulated/0/Documents/QtAgOpenGPS/Fields/<fieldDir>/`

`<fieldDir>` — это имя папки текущего поля (`FormGPS::currentFieldDirectory`).

## Моменты сохранения

1. **Закрытие поля / выход из программы** — `Yield::saveYieldData(currentFieldDirectory)` вызывается из `FormGPS::FileSaveField` (formgps.cpp:912) вместе с остальными файлами поля (Boundary, Sections, Contour, Tracks, Flags, KML).
2. **Автосохранение раз в 30 с** — в `tmrWatchdog_timeout` (formgps.cpp:470–479): каждые 120 тиков watchdog (250 мс), если `isJobStarted()` и `yieldDataDirty()`. Защита от потери данных при краше / убийстве процесса на Android.
3. **Удаление данных** — `deleteYieldData()` вызывается из `formgps_ui.cpp:666` при очистке данных поля (удаляет файл `YieldData.txt`).

`yieldDataDirty()` возвращает `true`, когда `m_savedRecordCount != m_records.size()`, т.е. после сохранения добавлены новые записи.

## Чтение при открытии поля

При загрузке поля (`formgps_saveopen.cpp:1264–1265`):
```cpp
Yield::instance()->loadYieldData(fieldDir);
Yield::instance()->recalculateAll();
```
- `loadYieldData` читает `YieldData.txt` в `m_records`.
- `recalculateAll` пересчитывает карту (треугольники на слое), суммарный `totalYield` (ц/ц) и `totalAreaHa` (га) из сохранённых записей, применяя текущие настройки `yield_sensorFactor` и `yield_grainTestWeight`.

## Формат файла YieldData.txt

Текст, ASCII, десятичная точка (QLocale::C), 6 знаков после запятой для double.

### Заголовок
```
$YieldData
<кол-во записей N>
```

### Записи (N штук)

Каждая запись — строка из 8 полей, разделённых запятыми:

| Поле | Тип | Описание |
|------|-----|----------|
| 0 | int | `pulseCount` — счётчик импульсов датчика из PGN 243 |
| 1 | double | `periodMs` — период измерения, мс |
| 2 | double | `lowTimeMs` — время низкого уровня датчика, мс (время контакта с зерном) |
| 3 | double | `speedKph` — средняя скорость за окно среза, км/ч |
| 4 | qint64 | `captureMs` — момент среза (Unix ms, с учётом задержки `yield_delayTime`) |
| 5 | double | `yieldCenHa` — урожайность патча, ц/га |
| 6 | double | `patchAreaM2` — площадь патча, м² (в старом формате отсутствует = 0) |
| 7 | int | количество команд отрисовки `cmds` для этой записи |

### Команды отрисовки (cmds.size() штук на каждую запись)

Сразу после строки записи идут строки команд, по 11 полей, разделённых запятыми:

| Поле | Тип | Описание |
|------|-----|----------|
| 0 | int | `type` — 0 = секция, 1 = зона |
| 1 | int | `index` — индекс секции (type=0) или зоны (type=1) |
| 2 | int | `startSection` — начальная секция (для зон) |
| 3 | int | `endSection` — конечная секция (для зон) |
| 4–6 | double | `left.x, left.y, left.z` — левая точка инструмента (локальные координаты) |
| 7–9 | double | `right.x, right.y, right.z` — правая точка инструмента |
| 10 | uint | `color.rgba()` — цвет патча (ARGB) |

### Пример

```
$YieldData
1
1234,2000.000000,850.000000,8.500000,1724160000000,35.250000,14.362500,1
1,3,2,4,-120.500000,10.000000,0.000000,-60.250000,12.500000,0.000000,4286611712
```

## Привязка к геометрии поля

Данные урожайности привязываются к геометрии поля напрямую — геометрия инструмента сохраняется **внутри каждой записи** (`cmds`), никакой отдельной привязки к логу позиций при загрузке не требуется.

### 1. Источник геометрии

Каждый фикс GPS в `formgps_position.cpp:1682-1710` пересчитывает точки секций орудия в локальных координатах поля (easting/northing, метры):

```
section[j].leftPoint  = (cosHeading × positionLeft  + easting, sinHeading × positionLeft  + northing)
section[j].rightPoint = (cosHeading × positionRight + easting, sinHeading × positionRight + northing)
```

Левая/правая точка секции = позиция трактора (easting/northing) + курс (heading) + фиксированные смещения орудия относительно оси трактора (`positionLeft`/`positionRight`).

### 2. Выбор геометрии "в момент среза"

PGN 243 приходит каждые 250 мс, но зерно было срезано `yield_delayTime` секунд назад. Поэтому:

- Каждый пакет пишет снапшот геометрии + скорости в кольцевой буфер 4 Гц (`pushWindowSample`, yield.cpp:217; `WINDOW_BUFFER_CAPACITY = 512` ≈ 128 с — больше максимальной задержки 60 с).
- `windowStateForCut(cutTimeMs, ...)` (yield.cpp:286) ищет в буфере сэмпл, ближайший к `captureMs = now - delayMs`, и берёт из него `cmds` — точки left/right активных секций и зон (`cmd.left`, `cmd.right`, yield.cpp:203-212).

### 3. Сохранение

В файл пишутся именно эти точки в локальных координатах поля (z = 0) + тип/индекс секции или зоны + цвет патча. Файл самодостаточен: для отрисовки не нужен лог позиций.

### 4. Отрисовка карты

- **Вживую** — `drawPatch` (yield.cpp:434) добавляет вершины (left/right точек) в yield-слой (`LayerService::addZoneVertices` / `addSectionVertices`). При смене набора покрытых секций буфер слоя сбрасывается, чтобы квады не соединялись через разрыв.
- **После загрузки из файла** — `recalculateAll` (yield.cpp:688): для каждой секции/зоны берёт пару последовательных записей и строит 2 треугольника:
  `(prev.left, prev.right, cmd.left)` + `(cmd.left, prev.right, cmd.right)` (yield.cpp:781-796) — получается непрерывный слой патчей вдоль траектории движения.
- Разрывы в `pulseCount` (> 2 пропущенных счёта) считаются физическим разрывом покрытия — цепочка квадов для секции/зоны обрывается (yield.cpp:740-748).

Координаты — те же локальные, что и у остальных файлов поля (Boundary, Sections, Contour), привязаны к началу координат поля через GPS-позицию трактора.

## Обратный процесс (loadYieldData)

- Проверяется заголовок `$YieldData`, иначе чтение прекращается (не ошибка — поле открыто впервые).
- Старый формат (7 полей в записи, без `patchAreaM2`) поддерживается: `patchAreaM2 = 0`, при пересчёте `recalculateAll` использует статическую формулу `площадь = скорость × эффективная_ширина × период`.
- После загрузки `m_lastRecordedPulseCount` устанавливается из последней записи.

## Связанные настройки

| Ключ QSettings | Описание |
|----------------|----------|
| `yield/isOn` | Включение отображения/записи урожайности |
| `yield/sensorFactor` | Л/с контакта датчика → объём патча |
| `yield/grainTestWeight` | Насыпная масса, кг/м³ |
| `yield/delayTime` | Задержка от среза до датчика, с (по умолчанию 8) |
| `yield/binCapacity` | Ёмкость бункера, л (калибровка) |
| `yield/colorStops` | Цветовая шкала карты |

## Формулы

- `patchVolumeL = lowTimeSec × sensorFactor`
- `patchMassKg = patchVolumeL × testWeight / 1000`
- `massFlowKgS = patchMassKg / periodSec`
- `yieldCenHa = patchMassKg / patchAreaM2 × 100`
- Запись не создаётся при средней скорости окна среза < 1 км/ч (`MIN_YIELD_SPEED_KPH`)

## Диагностика

Все события (вкл/выкл yield, калибровка, пропуски счётчиков, сохранения/загрузки) дополнительно пишутся в `YieldDiagnostics.txt` (та же папка Documents, отдельный от файлов поля журнал):
```
<Documents>/QtAgOpenGPS/YieldDiagnostics.txt
```
