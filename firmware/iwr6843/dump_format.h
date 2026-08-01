/* Stage-1c L3 burst-dump wire format.
 *
 * MUST stay byte-for-byte in sync with src/openflight/iwr6843/dump.py (HEADER =
 * struct.Struct("<4sHHHBBHBBHH")). Little-endian. 20-byte header, then payload:
 *   raw fmt:
 *     for each frame, each chirp, each rx: n_samples * (int16 Im, int16 Re).
 *   range-bin fmt 1:
 *     for each frame, each chirp, each rx: n_samples selected range bins *
 *     (int16 Im, int16 Re), where _pad carries the first range-bin index.
 *   range-bin fmt 2 (version 4+):
 *     n_frames uint8 start-bin values immediately follow this header, then
 *     the same frame/chirp/rx/IQ payload. Each frame can therefore retain a
 *     different contiguous range window without making the decoder guess.
 *   temperature extension (version 5+):
 *     a 24-byte temperature report immediately follows the fixed header.
 * Chirp order is TDM-interleaved: chirp c -> tx = c % n_tx, loop = c / n_tx.
 */
#ifndef L3_DUMP_FORMAT_H
#define L3_DUMP_FORMAT_H

#include <stdint.h>

#define L3_DUMP_MAGIC       "ILD1"
#define L3_DUMP_VERSION     3   /* v2: trigger_frame = oldest ring slot;
                                 * v3: frame_period_us populated */
#define L3_DUMP_VERSION_WINDOWED 4
#define L3_DUMP_VERSION_TEMPERATURE 5
#define L3_SAMPLE_INT16_IQ  0
#define L3_SAMPLE_RANGE_FFT_IQ16 1
#define L3_SAMPLE_RANGE_FFT_IQ16_WINDOWED 2

typedef struct __attribute__((packed)) {
    char     magic[4];          /* "ILD1" */
    uint16_t version;           /* L3_DUMP_VERSION */
    uint16_t n_frames;          /* frames in this dump window */
    uint16_t chirps_per_frame;  /* n_tx * loops */
    uint8_t  n_tx;
    uint8_t  n_rx;
    uint16_t n_samples;         /* ADC samples per chirp */
    uint8_t  sample_fmt;        /* L3_SAMPLE_INT16_IQ */
    uint8_t  _pad;              /* fmt 1: first range-bin index */
    uint16_t trigger_frame;     /* v2+: OLDEST ring slot = time-order start
                                 * (slots stream in memory order; rotate by
                                 * this to get chronological frames). 0 in v1. */
    uint16_t frame_period_us;   /* v3+: frame periodicity in microseconds
                                 * (self-describing timing for the range-walk
                                 * speed fit). 0 in v1/v2 dumps (was padding). */
} l3_dump_header_t;             /* sizeof == 20 */

typedef struct __attribute__((packed)) {
    uint32_t device_time_ms;    /* radarSS local time from powerup */
    /* TI mmWaveLink rlRfTempData_t temperature fields: signed, 1 LSB = 1 deg C. */
    int16_t  tmpRx0Sens;        /* RX0 temperature sensor reading */
    int16_t  tmpRx1Sens;        /* RX1 temperature sensor reading */
    int16_t  tmpRx2Sens;        /* RX2 temperature sensor reading */
    int16_t  tmpRx3Sens;        /* RX3 temperature sensor reading */
    int16_t  tmpTx0Sens;        /* TX0 temperature sensor reading */
    int16_t  tmpTx1Sens;        /* TX1 temperature sensor reading */
    int16_t  tmpTx2Sens;        /* TX2 temperature sensor reading */
    int16_t  tmpPmSens;         /* PM temperature sensor reading */
    int16_t  tmpDig0Sens;       /* Digital temperature sensor reading */
    int16_t  tmpDig1Sens;       /* Second digital temperature sensor reading */
} l3_temperature_report_t;      /* sizeof == 24 */

#endif /* L3_DUMP_FORMAT_H */
