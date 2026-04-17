package com.example.gsc_app2.utils

import android.graphics.Bitmap
import androidx.camera.core.ImageProxy
import java.io.ByteArrayOutputStream

object ImageUtils {
    fun toJpeg(image: ImageProxy, quality: Int = 60): ByteArray {
        val bitmap = image.toBitmap()
        val stream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.JPEG, quality, stream)
        return stream.toByteArray()
    }
}