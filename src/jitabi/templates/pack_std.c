
static JITABI_INLINE ssize_t encode_varuint32(unsigned long long val, char *out)
{
    size_t i = 0;
    do {
        unsigned char b = val & 0x7F;
        val >>= 7;
        if (val) b |= 0x80;
        out[i++] = b;
    } while (val);
    return i;
}

static JITABI_INLINE ssize_t encode_varint32(long long val, char *out)
{
    size_t i = 0;
    int more = 1;

    while (more) {
        unsigned char byte = val & 0x7F;
        int sign_bit = (byte & 0x40) != 0;

        val >>= 7;

        // Determine if more bytes are needed
        if ((val == 0 && !sign_bit) || (val == -1 && sign_bit)) {
            more = 0;
        } else {
            byte |= 0x80;
        }

        out[i++] = byte;
    }

    return (ssize_t)i;
}

static JITABI_INLINE ssize_t pack_bool(PyObject *obj, char *out, size_t out_len)
{
    int res = PyObject_IsTrue(obj);
    if (res < 0) return -1;
    out[0] = (char)(res ? 1 : 0);
    return 1;
}

static JITABI_INLINE ssize_t pack_uint8(PyObject *obj, char *out, size_t out_len)
{
    unsigned long val = PyLong_AsUnsignedLong(obj);
    if (PyErr_Occurred()) return -1;
    if (val > 0xFF) {
        PyErr_SetString(PyExc_OverflowError, "uint8 out of range");
        return -1;
    }
    out[0] = (unsigned char)val;
    return 1;
}

static JITABI_INLINE ssize_t pack_uint16(PyObject *obj, char *out, size_t out_len)
{
    unsigned long val = PyLong_AsUnsignedLong(obj);
    if (PyErr_Occurred()) return -1;
    if (val > 0xFFFF) {
        PyErr_SetString(PyExc_OverflowError, "uint16 out of range");
        return -1;
    }

    uint16_t u16 = (uint16_t)val;
    out[0] = (char)(u16 & 0xFF);
    out[1] = (char)((u16 >> 8) & 0xFF);
    return 2;
}

static JITABI_INLINE ssize_t pack_uint32(PyObject *obj, char *out, size_t out_len)
{
    unsigned long val = PyLong_AsUnsignedLong(obj);
    if (PyErr_Occurred()) return -1;

#if defined(_WIN32) || defined(_WIN64)
    // On LLP64 platforms like Windows, PyLong_AsUnsignedLong may truncate >32-bit
    if (val > 0xFFFFFFFFUL) {
        PyErr_SetString(PyExc_OverflowError, "uint32 out of range");
        return -1;
    }
#endif

    uint32_t u32 = (uint32_t)val;
    out[0] = (char)(u32 & 0xFF);
    out[1] = (char)((u32 >> 8) & 0xFF);
    out[2] = (char)((u32 >> 16) & 0xFF);
    out[3] = (char)((u32 >> 24) & 0xFF);
    return 4;
}

static JITABI_INLINE ssize_t pack_uint64(PyObject *obj, char *out, size_t out_len)
{
    unsigned long long val = PyLong_AsUnsignedLongLong(obj);
    if (PyErr_Occurred()) return -1;

    uint64_t u64 = (uint64_t)val;
    out[0] = (char)(u64 & 0xFF);
    out[1] = (char)((u64 >> 8) & 0xFF);
    out[2] = (char)((u64 >> 16) & 0xFF);
    out[3] = (char)((u64 >> 24) & 0xFF);
    out[4] = (char)((u64 >> 32) & 0xFF);
    out[5] = (char)((u64 >> 40) & 0xFF);
    out[6] = (char)((u64 >> 48) & 0xFF);
    out[7] = (char)((u64 >> 56) & 0xFF);
    return 8;
}

static JITABI_INLINE ssize_t
pack_uint128(PyObject *obj, char *out, size_t out_len)
{
    if (out_len < 16) {
        PyErr_SetString(PyExc_ValueError, "output buffer too small");
        return -1;
    }
    if (!PyLong_Check(obj)) {
        PyErr_SetString(PyExc_TypeError, "expected int for uint128");
        return -1;
    }

    /* low 64 bits  */
    PyObject *mask_lo = PyLong_FromUnsignedLongLong(0xFFFFFFFFFFFFFFFFULL);
    if (!mask_lo) return -1;
    PyObject *lo_obj  = PyNumber_And(obj, mask_lo);
    Py_DECREF(mask_lo);
    if (!lo_obj) return -1;

    /* high 64 bits */
    PyObject *shift_amt = PyLong_FromLong(64);
    if (!shift_amt) { Py_DECREF(lo_obj); return -1; }
    PyObject *hi_obj    = PyNumber_Rshift(obj, shift_amt);
    Py_DECREF(shift_amt);
    if (!hi_obj) { Py_DECREF(lo_obj); return -1; }

    uint64_t lo = PyLong_AsUnsignedLongLong(lo_obj);
    uint64_t hi = PyLong_AsUnsignedLongLong(hi_obj);
    Py_DECREF(lo_obj); Py_DECREF(hi_obj);
    if (PyErr_Occurred()) return -1;

    memcpy(out,      &lo, 8);
    memcpy(out + 8,  &hi, 8);
    return 16;
}

static JITABI_INLINE ssize_t pack_int8(PyObject *obj, char *out, size_t out_len)
{
    long val = PyLong_AsLong(obj);
    if (PyErr_Occurred()) return -1;
    if (val < -128 || val > 127) {
        PyErr_SetString(PyExc_OverflowError, "int8 out of range");
        return -1;
    }
    out[0] = (signed char)val;
    return 1;
}

static JITABI_INLINE ssize_t pack_int16(PyObject *obj, char *out, size_t out_len)
{
    long val = PyLong_AsLong(obj);
    if (PyErr_Occurred()) return -1;
    if (val < -32768 || val > 32767) {
        PyErr_SetString(PyExc_OverflowError, "int16 out of range");
        return -1;
    }

    int16_t i16 = (int16_t)val;
    out[0] = (char)(i16 & 0xFF);
    out[1] = (char)((i16 >> 8) & 0xFF);
    return 2;
}

static JITABI_INLINE ssize_t pack_int32(PyObject *obj, char *out, size_t out_len)
{
    long val = PyLong_AsLong(obj);
    if (PyErr_Occurred()) return -1;

    if (val < INT32_MIN || val > INT32_MAX) {
        PyErr_SetString(PyExc_OverflowError, "int32 out of range");
        return -1;
    }

    int32_t i32 = (int32_t)val;
    out[0] = (char)(i32 & 0xFF);
    out[1] = (char)((i32 >> 8) & 0xFF);
    out[2] = (char)((i32 >> 16) & 0xFF);
    out[3] = (char)((i32 >> 24) & 0xFF);
    return 4;
}

static JITABI_INLINE ssize_t pack_int64(PyObject *obj, char *out, size_t out_len)
{
    long long val = PyLong_AsLongLong(obj);
    if (PyErr_Occurred()) return -1;

    int64_t i64 = (int64_t)val;
    out[0] = (char)(i64 & 0xFF);
    out[1] = (char)((i64 >> 8) & 0xFF);
    out[2] = (char)((i64 >> 16) & 0xFF);
    out[3] = (char)((i64 >> 24) & 0xFF);
    out[4] = (char)((i64 >> 32) & 0xFF);
    out[5] = (char)((i64 >> 40) & 0xFF);
    out[6] = (char)((i64 >> 48) & 0xFF);
    out[7] = (char)((i64 >> 56) & 0xFF);
    return 8;
}

static JITABI_INLINE ssize_t
pack_int128(PyObject *obj, char *out, size_t out_len)
{
    if (out_len < 16) {
        PyErr_SetString(PyExc_ValueError, "output buffer too small");
        return -1;
    }
    if (!PyLong_Check(obj)) {
        PyErr_SetString(PyExc_TypeError, "expected int for int128");
        return -1;
    }

    PyObject *zero = PyLong_FromLong(0);
    if (!zero) return -1;
    const int sign = PyObject_RichCompareBool(obj, zero, Py_LT);
    Py_DECREF(zero);
    if (sign < 0) return -1;

    PyObject *abs_obj = sign
        ? PyNumber_Negative(obj)
        : obj;
    if (!abs_obj) return -1;
    /* now we own one ref in both cases */

    /* magnitude halves                                                  */
    PyObject *lo_obj = PyNumber_And(
        abs_obj, PyLong_FromUnsignedLongLong(0xFFFFFFFFFFFFFFFFULL));
    if (!lo_obj) { Py_DECREF(abs_obj); return -1; }

    PyObject *hi_obj = PyNumber_Rshift(abs_obj, PyLong_FromLong(64));
    if (!hi_obj) { Py_DECREF(abs_obj); Py_DECREF(lo_obj); return -1; }

    uint64_t lo = PyLong_AsUnsignedLongLong(lo_obj);
    uint64_t hi = PyLong_AsUnsignedLongLong(hi_obj);
    Py_DECREF(abs_obj); Py_DECREF(lo_obj); Py_DECREF(hi_obj);
    if (PyErr_Occurred()) return -1;

    if (sign) {                                   /* two’s complement      */
        lo = ~lo;
        hi = ~hi;
        lo += 1;
        if (lo == 0) hi += 1;
    }

    memcpy(out,     &lo, 8);
    memcpy(out + 8, &hi, 8);
    return 16;
}

static JITABI_INLINE ssize_t pack_varuint32(PyObject *obj, char *out, size_t out_len)
{
    unsigned long long val = PyLong_AsUnsignedLongLong(obj);
    if (PyErr_Occurred()) return -1;

    return encode_varuint32(val, out);
}

static JITABI_INLINE ssize_t pack_varint32(PyObject *obj, char *out, size_t out_len)
{
    long long val = PyLong_AsLongLong(obj);
    if (PyErr_Occurred()) return -1;

    return encode_varint32(val, out);
}

static JITABI_INLINE ssize_t pack_float32(PyObject *obj, char *out, size_t out_len)
{
    float f = (float)PyFloat_AsDouble(obj);
    if (PyErr_Occurred()) return -1;
    memcpy(out, &f, 4);
    return 4;
}

static JITABI_INLINE ssize_t pack_float64(PyObject *obj, char *out, size_t out_len)
{
    double d = PyFloat_AsDouble(obj);
    if (PyErr_Occurred()) return -1;
    memcpy(out, &d, 8);
    return 8;
}

static JITABI_INLINE ssize_t pack_raw(PyObject *obj, size_t len, char *out, size_t out_len)
{
    if (!PyBytes_Check(obj)) {
        PyErr_SetString(PyExc_TypeError, "expected a bytes object");
        return -1;
    }

    Py_ssize_t size;
    char *data;
    if (PyBytes_AsStringAndSize(obj, &data, &size) < 0)
        return -1;

    if ((size_t)size > out_len) {
        PyErr_SetString(PyExc_ValueError, "output buffer too small for raw data");
        return -1;
    }

    memcpy(out, data, (size_t)size);
    return size;
}

static JITABI_INLINE ssize_t pack_bytes(PyObject *obj, char *out, size_t out_len)
{
    if (!PyBytes_Check(obj)) {
        PyErr_SetString(PyExc_TypeError, "expected a bytes object");
        return -1;
    }

    Py_ssize_t size;
    char *data;
    if (PyBytes_AsStringAndSize(obj, &data, &size) < 0)
        return -1;

    char len_buf[10];
    ssize_t len_len = encode_varuint32((unsigned long long)size, len_buf);

    if ((size_t)(len_len + size) > out_len) {
        PyErr_SetString(PyExc_ValueError, "output buffer too small for bytes");
        return -1;
    }

    memcpy(out, len_buf, (size_t)len_len);
    memcpy(out + len_len, data, (size_t)size);

    return len_len + size;
}

static JITABI_INLINE ssize_t pack_string(PyObject *obj, char *out, size_t out_len)
{
    if (!PyUnicode_Check(obj)) {
        PyErr_SetString(PyExc_TypeError, "expected a string");
        return -1;
    }

    Py_ssize_t size;
    const char *utf8 = PyUnicode_AsUTF8AndSize(obj, &size);
    if (!utf8)
        return -1;

    char len_buf[10];
    ssize_t len_len = encode_varuint32((unsigned long long)size, len_buf);

    if ((size_t)(len_len + size) > out_len) {
        PyErr_SetString(PyExc_ValueError, "output buffer too small for string");
        return -1;
    }

    memcpy(out, len_buf, (size_t)len_len);
    memcpy(out + len_len, utf8, (size_t)size);

    return len_len + size;
}


// default structs

static ssize_t pack_asset(PyObject *__obj, char *__dst, size_t __dst_len)
{

    ssize_t __offset = 0;
    ssize_t __consumed = 0;

    JITABI_LOG_DEBUG("PACK struct asset:");



    PyObject *__field = NULL;


    {
        // -------- field "amount": "int64" --------

        JITABI_LOG_DEBUG(
            "%s: %s",
            "amount",
            "int64"
        );

        __field = PyDict_GetItemString(__obj, "amount");
        if (!__field) {
            PyErr_SetString(PyExc_KeyError, "missing field 'amount'");
            return -1;
        }
        __consumed = pack_int64(
            __field
            , __dst + __offset
            , __dst_len - __offset
        );

        if (__consumed < 0) return -1;
        __offset += __consumed;
        JITABI_LOG_DEBUG("amount packed, offset: %lu", __offset);
    }
    {
        // -------- field "symbol": "symbol" --------

        JITABI_LOG_DEBUG(
            "%s: %s",
            "symbol",
            "symbol"
        );

        __field = PyDict_GetItemString(__obj, "symbol");
        if (!__field) {
            PyErr_SetString(PyExc_KeyError, "missing field 'symbol'");
            return -1;
        }
        __consumed = pack_uint64(
            __field
            , __dst + __offset
            , __dst_len - __offset
        );

        if (__consumed < 0) return -1;
        __offset += __consumed;
        JITABI_LOG_DEBUG("symbol packed, offset: %lu", __offset);
    }

    return __offset;
}

static ssize_t pack_extended_asset(PyObject *__obj, char *__dst, size_t __dst_len)
{

    ssize_t __offset = 0;
    ssize_t __consumed = 0;

    JITABI_LOG_DEBUG("PACK struct extended_asset:");



    PyObject *__field = NULL;


    {
        // -------- field "quantity": "asset" --------

        JITABI_LOG_DEBUG(
            "%s: %s",
            "quantity",
            "asset"
        );

        __field = PyDict_GetItemString(__obj, "quantity");
        if (!__field) {
            PyErr_SetString(PyExc_KeyError, "missing field 'quantity'");
            return -1;
        }
        __consumed = pack_asset(
            __field
            , __dst + __offset
            , __dst_len - __offset
        );

        if (__consumed < 0) return -1;
        __offset += __consumed;
        JITABI_LOG_DEBUG("quantity packed, offset: %lu", __offset);
    }
    {
        // -------- field "contract": "name" --------

        JITABI_LOG_DEBUG(
            "%s: %s",
            "contract",
            "name"
        );

        __field = PyDict_GetItemString(__obj, "contract");
        if (!__field) {
            PyErr_SetString(PyExc_KeyError, "missing field 'contract'");
            return -1;
        }
        __consumed = pack_uint64(
            __field
            , __dst + __offset
            , __dst_len - __offset
        );

        if (__consumed < 0) return -1;
        __offset += __consumed;
        JITABI_LOG_DEBUG("contract packed, offset: %lu", __offset);
    }

    return __offset;
}


// default aliases

static ssize_t pack_float128(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 16, __dst, __dst_len);
}

static ssize_t pack_name(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_uint64(__obj, __dst, __dst_len);
}

static ssize_t pack_account_name(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_uint64(__obj, __dst, __dst_len);
}

static ssize_t pack_symbol(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_uint64(__obj, __dst, __dst_len);
}

static ssize_t pack_symbol_code(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_uint64(__obj, __dst, __dst_len);
}

static ssize_t pack_rd160(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 20, __dst, __dst_len);
}

static ssize_t pack_checksum160(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 20, __dst, __dst_len);
}

static ssize_t pack_sha256(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 32, __dst, __dst_len);
}

static ssize_t pack_checksum256(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 32, __dst, __dst_len);
}

static ssize_t pack_checksum512(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 64, __dst, __dst_len);
}

static ssize_t pack_time_point(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_uint64(__obj, __dst, __dst_len);
}

static ssize_t pack_time_point_sec(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_uint32(__obj, __dst, __dst_len);
}

static ssize_t pack_block_timestamp_type(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_uint32(__obj, __dst, __dst_len);
}

static ssize_t pack_public_key(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 34, __dst, __dst_len);
}

static ssize_t pack_signature(PyObject *__obj, char *__dst, size_t __dst_len)
{
    return pack_raw(__obj, 66, __dst, __dst_len);
}
