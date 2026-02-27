package com.example.android

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.net.wifi.WifiManager
import android.os.Bundle
import android.text.format.Formatter
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Info
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.example.android.ui.theme.AndroidTheme
// --- השורה החדשה: ייבוא המנוע מהספרייה החיצונית ---
import com.example.tausync_lib.TauSyncJavaEngine
import com.example.tausync_lib.models.TransferRequest
import com.example.tausync_lib.implementations.management.ConnectionManager

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.time.delay
import kotlinx.coroutines.withContext

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        setContent {
            AndroidTheme {
                Scaffold(
                    modifier = Modifier.fillMaxSize(),
                    containerColor = MaterialTheme.colorScheme.background
                ) { innerPadding ->
                    IPDashboard(modifier = Modifier.padding(innerPadding))
                }
            }
        }
    }
}

@Composable
fun IPDashboard(modifier: Modifier = Modifier) {
    val context = LocalContext.current

// --- יצירת ה-Engine וניהול הסטטוס ---
    val javaEngine = remember { TauSyncJavaEngine() }
    var connection by remember { mutableStateOf<ConnectionManager?>(null) }

// משתנה State כדי לוודא שאנחנו שולחים רק פעם אחת
    var hasSentHello by remember { mutableStateOf(false) }

// 1. אתחול ה-Connection (רץ פעם אחת כשהמסך עולה)
    LaunchedEffect(Unit) {
        withContext(Dispatchers.IO) {
            val manager = ConnectionManager() // וודא שזה מבצע Initialize ו-Connect בפועל
            connection = manager
        }
    }

// 2. לוגיקת שליחת ההודעה - תלויה בשינוי של ה-connection
    LaunchedEffect(connection) {
        val currentConnection = connection

        // אם יש חיבור ועדיין לא שלחנו את הודעת הברכה
        if (currentConnection != null && !hasSentHello) {
            hasSentHello = true // מסמנים מיד כדי שלא יישלח פעמיים

            withContext(Dispatchers.IO) {
                try {
                    val message = "hello from the other side"
                    val inputStream = message.toByteArray(Charsets.UTF_8).inputStream()
                    val request = TransferRequest() // ייצור UUID אוטומטי ל-Handshake
                    delay(2000)
                    // הקריאה למתודה שבנינו - עושה Handshake מול ה-C# ואז מרימה את הסטרים
                    currentConnection.smartSend(inputStream, request)

                    println("הודעה נשלחה בהצלחה ל-Windows! 🦾")
                } catch (e: Exception) {
                    println("שגיאה בשליחה: ${e.message}")
                    hasSentHello = false // מאפשר ניסיון חוזר במקרה של תקלה
                }
            }
        }
    }

// --- הממשק (UI) ---
    Column {
        if (connection == null) {
            Text("מתחבר לשרת Windows...")
        } else {
            Text("השרת למעלה! ✅")
            if (hasSentHello) {
                Text("הודעת 'Hello' נשלחה בהצלחה.")
            }
        }
    }
    val engineStatus = remember { javaEngine.statusMessage } // Java getters הופכים ל-properties ב-Kotlin

    var ipAddress by remember { mutableStateOf(getLocalIpAddress(context)) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Icon(
            imageVector = Icons.Default.Info,
            contentDescription = null,
            tint = MaterialTheme.colorScheme.primary,
            modifier = Modifier.size(64.dp)
        )

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = "Network Status",
            style = MaterialTheme.typography.headlineMedium,
            fontWeight = FontWeight.Bold
        )

        Spacer(modifier = Modifier.height(24.dp))

        // ה-Card הקיים שלך
        ElevatedCard(
            modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(24.dp),
            colors = CardDefaults.elevatedCardColors(
                containerColor = MaterialTheme.colorScheme.surfaceVariant
            )
        ) {
            Column(
                modifier = Modifier.padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = "LOCAL IP ADDRESS",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.secondary
                )

                Text(
                    text = ipAddress,
                    style = MaterialTheme.typography.displaySmall.copy(
                        fontWeight = FontWeight.ExtraBold,
                        letterSpacing = 1.sp
                    ),
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(modifier = Modifier.height(16.dp))

                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Button(
                        onClick = { copyToClipboard(context, ipAddress) },
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Text("Copy IP")
                    }

                    // Refresh Button
                    OutlinedButton(
                        onClick = { ipAddress = getLocalIpAddress(context) },
                        shape = RoundedCornerShape(12.dp)
                    ) {
                        Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(4.dp))
                        Text("Refresh")
                    }
                }
            }
        }

        // --- כאן הוספתי את ההודעה מה-Java Engine בתחתית ---
        Spacer(modifier = Modifier.height(32.dp))

        HorizontalDivider(modifier = Modifier.padding(horizontal = 40.dp), thickness = 1.dp)

        Spacer(modifier = Modifier.height(16.dp))

        Text(
            text = engineStatus,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.outline,
            fontWeight = FontWeight.Medium
        )
    }
}

fun getLocalIpAddress(context: Context): String {
    return try {
        val wifiManager = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val ipInt = wifiManager.connectionInfo.ipAddress
        if (ipInt == 0) "Disconnected" else Formatter.formatIpAddress(ipInt)
    } catch (e: Exception) {
        "Unknown"
    }
}

fun copyToClipboard(context: Context, text: String) {
    val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    val clip = ClipData.newPlainText("IP Address", text)
    clipboard.setPrimaryClip(clip)
    Toast.makeText(context, "Copied to clipboard!", Toast.LENGTH_SHORT).show()
}