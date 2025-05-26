JITABI_INLINE_ALWAYS uint16_t read_le16(const char *p) {
#if defined(__x86_64__)
    return *(const uint16_t *)p;
#else
    uint16_t v;
    memcpy(&v, p, 2);
    return v;
#endif
}

JITABI_INLINE_ALWAYS uint32_t read_le32(const char *p) {
#if defined(__x86_64__)
    return *(const uint32_t *)p;
#else
    uint32_t v;
    memcpy(&v, p, 4);
    return v;
#endif
}

JITABI_INLINE_ALWAYS uint64_t read_le64(const char *p) {
#if defined(__x86_64__)
    return *(const uint64_t *)p;
#else
    uint64_t v;
    memcpy(&v, p, 8);
    return v;
#endif
}

JITABI_INLINE_ALWAYS PyObject *uint128_from_halves(uint64_t hi, uint64_t lo)
{
    PyObject *py_hi  = PyLong_FromUnsignedLongLong(hi);
    if (!py_hi) return NULL;

    PyObject *shift  = PyLong_FromLong(64);
    if (!shift) { Py_DECREF(py_hi); return NULL; }

    PyObject *py_hi_shifted = PyNumber_Lshift(py_hi, shift);
    Py_DECREF(py_hi); Py_DECREF(shift);
    if (!py_hi_shifted) return NULL;

    PyObject *py_lo  = PyLong_FromUnsignedLongLong(lo);
    if (!py_lo) { Py_DECREF(py_hi_shifted); return NULL; }

    PyObject *res = PyNumber_Add(py_hi_shifted, py_lo);
    Py_DECREF(py_hi_shifted); Py_DECREF(py_lo);
    return res;  // new ref or NULL
}

JITABI_INLINE_ALWAYS PyObject *int128_from_halves(uint64_t hi, uint64_t lo)
{
    // sign bit lives in the high half
    const bool negative = (hi & 0x8000000000000000ULL) != 0;

    if (!negative)  // fast path for non-negative numbers
        return uint128_from_halves(hi, lo);

    // two’s complement -> magnitude
    hi = ~hi; lo = ~lo;
    lo += 1;
    if (lo == 0)  // propagate carry
        hi += 1;

    PyObject *mag = uint128_from_halves(hi, lo);
    if (!mag) return NULL;
    PyObject *neg = PyNumber_Negative(mag);
    Py_DECREF(mag);
    return neg;  // new ref or NULL
}

JITABI_INLINE_ALWAYS unsigned long long decode_varuint32(const char *restrict p, size_t *consumed)
{
    const unsigned char *s = (const unsigned char *)p;
    unsigned long long r = 0;
    unsigned char b;
    unsigned shift = 0;

    /* first byte (-90 % of the time) */
    b  = *s++;
    r  =  b & 0x7F;
    if (!(b & 0x80)) {
        if (consumed) *consumed = 1;
        return r;
    }
    shift = 7;

    /* remaining bytes (rare) */
    while ( (b = *s++) & 0x80 ) {
        r |= ((unsigned long long)(b & 0x7F)) << shift;
        shift += 7;
    }
    r |= ((unsigned long long)b) << shift;

    if (consumed) *consumed = (size_t)(s - (const unsigned char *)p);
    return r;
}

JITABI_INLINE_ALWAYS long long decode_varint32(const char *restrict p, size_t *consumed)
{
    const unsigned char *s = (const unsigned char *)p;
    long long r = 0;
    unsigned char b;
    unsigned shift = 0;

    /* first byte fast-path */
    b  = *s++;
    r  =  b & 0x7F;
    if (!(b & 0x80)) {
        if (b & 0x40)   /* sign-extend negative single-byte values */
            r |= -1LL << 7;
        if (consumed) *consumed = 1;
        return r;
    }
    shift = 7;

    /* remaining bytes */
    while ( (b = *s++) & 0x80 ) {
        r |= ((long long)(b & 0x7F)) << shift;
        shift += 7;
    }
    r |= ((long long)b & 0x7F) << shift;

    /* final sign-extension if negative */
    if ((b & 0x40) && (shift + 7 < sizeof(long long) * 8))
        r |= -1LL << (shift + 7);

    if (consumed) *consumed = (size_t)(s - (const unsigned char *)p);
    return r;
}

JITABI_INLINE_ALWAYS PyObject *unpack_bool (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 1;  return PyBool_FromLong(b[0] != 0); }

JITABI_INLINE_ALWAYS PyObject *unpack_uint8 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 1;  return PyLong_FromUnsignedLong((unsigned char)b[0]); }

JITABI_INLINE_ALWAYS PyObject *unpack_uint16 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 2;  return PyLong_FromUnsignedLong(read_le16(b)); }

JITABI_INLINE_ALWAYS PyObject *unpack_uint32 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 4;  return PyLong_FromUnsignedLong(read_le32(b)); }

JITABI_INLINE_ALWAYS PyObject *unpack_uint64 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 8;  return PyLong_FromUnsignedLongLong(read_le64(b)); }

JITABI_INLINE_ALWAYS PyObject *
unpack_uint128(const char *b, size_t buf_len, size_t *c)
{
    if (buf_len < 16) {
        PyErr_SetString(PyExc_ValueError, "buffer too small for uint128");
        return NULL;
    }
    uint64_t lo = read_le64(b);
    uint64_t hi = read_le64(b + 8);
    if (c) *c = 16;
    return uint128_from_halves(hi, lo);
}

JITABI_INLINE_ALWAYS PyObject *unpack_int8 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 1;  return PyLong_FromLong((signed char)b[0]); }

JITABI_INLINE_ALWAYS PyObject *unpack_int16 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 2;  return PyLong_FromLong((int16_t)read_le16(b)); }

JITABI_INLINE_ALWAYS PyObject *unpack_int32 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 4;  return PyLong_FromLong((int32_t)read_le32(b)); }

JITABI_INLINE_ALWAYS PyObject *unpack_int64 (const char *b, size_t buf_len, size_t *c)
{ if (c) *c = 8;  return PyLong_FromLongLong((int64_t)read_le64(b)); }

JITABI_INLINE_ALWAYS PyObject *
unpack_int128(const char *b, size_t buf_len, size_t *c)
{
    if (buf_len < 16) {
        PyErr_SetString(PyExc_ValueError, "buffer too small for int128");
        return NULL;
    }
    uint64_t lo = read_le64(b);
    uint64_t hi = read_le64(b + 8);
    if (c) *c = 16;
    return int128_from_halves(hi, lo);
}

JITABI_INLINE_ALWAYS PyObject *unpack_varuint32 (const char *b, size_t buf_len, size_t *c)
{
    unsigned long long v = decode_varuint32(b, c);
    return PyLong_FromUnsignedLongLong(v);
}

JITABI_INLINE_ALWAYS PyObject *unpack_varint32 (const char *b, size_t buf_len, size_t *c)
{
    long long v = decode_varint32(b, c);
    return PyLong_FromLongLong(v);
}

JITABI_INLINE_ALWAYS PyObject *unpack_float32 (const char *b, size_t buf_len, size_t *c)
{
    if (c) *c = 4;
    float f;
    memcpy(&f, b, 4);
    return PyFloat_FromDouble((double)f);
}

JITABI_INLINE_ALWAYS PyObject *unpack_float64 (const char *b, size_t buf_len, size_t *c)
{
    if (c) *c = 8;
    double d;
    memcpy(&d, b, 8);
    return PyFloat_FromDouble(d);
}

JITABI_INLINE_ALWAYS PyObject *unpack_raw (const char *b, size_t len, size_t buf_len, size_t *c)
{
    if (c) *c = len;
    return PyBytes_FromStringAndSize(b, len);
}

JITABI_INLINE_ALWAYS PyObject *unpack_bytes (const char *b, size_t buf_len, size_t *c)
{
    size_t len_consumed = 0;
    unsigned long long l = decode_varuint32(b, &len_consumed);

    JITABI_LOG_DEBUG("leb consumed: %lu", len_consumed);
    JITABI_LOG_DEBUG("about to unpack bytes of size: %llu", l);

    if (l > PY_SSIZE_T_MAX ||
        l > (unsigned long long)(buf_len - len_consumed)) {
        PyErr_SetString(PyExc_ValueError, "buffer too small for encoded length");
        return NULL;
    }

    if (c) *c = len_consumed + (size_t)l;
    return PyBytes_FromStringAndSize(b + len_consumed, (Py_ssize_t)l);
}

JITABI_INLINE_ALWAYS PyObject *unpack_string (const char *b, size_t buf_len, size_t *c)
{
    size_t len_consumed = 0;
    unsigned long long l = decode_varuint32(b, &len_consumed);

    if (l > PY_SSIZE_T_MAX ||
        l > (unsigned long long)(buf_len - len_consumed)) {
        PyErr_SetString(PyExc_ValueError, "buffer too small for encoded length");
        return NULL;
    }

    if (c) *c = len_consumed + (size_t)l;
    return PyUnicode_DecodeUTF8(b + len_consumed, (Py_ssize_t)l, "strict");
}


// default structs

JITABI_INLINE
PyObject *unpack_asset(const char *b, size_t buf_len, size_t *c)
{

    size_t __consumed = 0;
    size_t __total = 0;
    #ifdef __JITABI_DEBUG
    size_t __start_total = 0;
    #endif

    JITABI_LOG_DEBUG("UNPACK struct asset, buf_len: %lu", buf_len
    );


    // build python dict
    PyObject *__dict = PyDict_New();
    if (!__dict) goto error;

    PyObject *____amount = NULL;
    PyObject *____symbol = NULL;

    // -------- field "amount": "int64" --------

    JITABI_LOG_DEBUG(
        "%s: %s",
        "amount",
        "int64"
    );

    ____amount = unpack_int64(
        b + __total,
        buf_len - __total,
        &__consumed
    );

    if (!____amount) goto error;
    __total += __consumed;

    JITABI_LOG_DEBUG(
        "amount start: %lu, size: %lu, total: %lu",
        __start_total,
        __total - __start_total,
        __total
    );

    // -------- field "symbol": "symbol" --------

    JITABI_LOG_DEBUG(
        "%s: %s",
        "symbol",
        "symbol"
    );

    ____symbol = unpack_uint64(
        b + __total,
        buf_len - __total,
        &__consumed
    );

    if (!____symbol) goto error;
    __total += __consumed;

    JITABI_LOG_DEBUG(
        "symbol start: %lu, size: %lu, total: %lu",
        __start_total,
        __total - __start_total,
        __total
    );

    // -------- end of fields unpacking ---------

    // set total bytes consumed
    if (c) *c = __total;

    // set items
    if (PyDict_SetItemString(__dict, "amount", ____amount) < 0) goto error;
    if (PyDict_SetItemString(__dict, "symbol", ____symbol) < 0) goto error;

    JITABI_LOG_DEBUG("fields set on dict");

    // drop local refs now owned by dict
    Py_DECREF(____amount);
    Py_DECREF(____symbol);
    return __dict;

error:
    PyErr_SetString(PyExc_RuntimeError, "While unpacking asset");
    Py_XDECREF(____amount);
    Py_XDECREF(____symbol);
    Py_XDECREF(__dict);
    return NULL;

}

JITABI_INLINE
PyObject *unpack_extended_asset(const char *b, size_t buf_len, size_t *c)
{

    size_t __consumed = 0;
    size_t __total = 0;
    #ifdef __JITABI_DEBUG
    size_t __start_total = 0;
    #endif

    JITABI_LOG_DEBUG("UNPACK struct extended_asset, buf_len: %lu", buf_len
    );


    // build python dict
    PyObject *__dict = PyDict_New();
    if (!__dict) goto error;

    PyObject *____quantity = NULL;
    PyObject *____contract = NULL;

    // -------- field "quantity": "asset" --------

    JITABI_LOG_DEBUG(
        "%s: %s",
        "quantity",
        "asset"
    );

    ____quantity = unpack_asset(
        b + __total,
        buf_len - __total,
        &__consumed
    );

    if (!____quantity) goto error;
    __total += __consumed;

    JITABI_LOG_DEBUG(
        "quantity start: %lu, size: %lu, total: %lu",
        __start_total,
        __total - __start_total,
        __total
    );

    // -------- field "contract": "name" --------

    JITABI_LOG_DEBUG(
        "%s: %s",
        "contract",
        "name"
    );

    ____contract = unpack_uint64(
        b + __total,
        buf_len - __total,
        &__consumed
    );

    if (!____contract) goto error;
    __total += __consumed;

    JITABI_LOG_DEBUG(
        "contract start: %lu, size: %lu, total: %lu",
        __start_total,
        __total - __start_total,
        __total
    );

    // -------- end of fields unpacking ---------

    // set total bytes consumed
    if (c) *c = __total;

    // set items
    if (PyDict_SetItemString(__dict, "quantity", ____quantity) < 0) goto error;
    if (PyDict_SetItemString(__dict, "contract", ____contract) < 0) goto error;

    JITABI_LOG_DEBUG("fields set on dict");

    // drop local refs now owned by dict
    Py_DECREF(____quantity);
    Py_DECREF(____contract);
    return __dict;

error:
    PyErr_SetString(PyExc_RuntimeError, "While unpacking extended_asset");
    Py_XDECREF(____quantity);
    Py_XDECREF(____contract);
    Py_XDECREF(__dict);
    return NULL;

}


// default aliases

JITABI_INLINE
PyObject *unpack_float128(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 16, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_name(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_uint64(
        __buf, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_account_name(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_uint64(
        __buf, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_symbol(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_uint64(
        __buf, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_symbol_code(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_uint64(
        __buf, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_rd160(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 20, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_checksum160(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 20, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_sha256(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 32, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_checksum256(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 32, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_checksum512(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 64, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_time_point(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_uint64(
        __buf, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_time_point_sec(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_uint32(
        __buf, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_block_timestamp_type(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_uint32(
        __buf, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_public_key(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 34, __buf_len, __consumed
    );
}

JITABI_INLINE
PyObject *unpack_signature(const char *__buf, size_t __buf_len, size_t *__consumed)
{
    return unpack_raw(
        __buf, 66, __buf_len, __consumed
    );
}
