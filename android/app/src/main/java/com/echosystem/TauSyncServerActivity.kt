package com.echosystem

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import com.tausync.implementations.management.ConnectionManager
import com.tausync.implementations.security.SecureChannel
import com.tausync.implementations.transport.SocketTransport
import com.tausync.interfaces.IConnectionManager
import com.tausync.interfaces.ISecureChannel
import com.tausync.interfaces.ITransport
import com.tausync.models.TransferRequest
import java.net.ServerSocket
import java.nio.charset.StandardCharsets
import java.security.SecureRandom

class TauSyncServerActivity : AppCompatActivity() {
    private var connectionManager: IConnectionManager? = null
    private var transport: ITransport? = null
    private var secureChannel: ISecureChannel? = null
    private var serverThread: Thread? = null
    private var isServerRunning = false
    
    private lateinit var statusText: TextView
    private lateinit var messageInput: EditText
    private lateinit var sendButton: Button
    private lateinit var receivedText: TextView
    private lateinit var startServerButton: Button
    private lateinit var ipAddressText: TextView
    
    private var sharedKey: ByteArray? = null
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_tausync)
        
        // Initialize UI
        statusText = findViewById(R.id.statusText)
        messageInput = findViewById(R.id.messageInput)
        sendButton = findViewById(R.id.sendButton)
        receivedText = findViewById(R.id.receivedText)
        startServerButton = findViewById(R.id.connectButton)
        ipAddressText = TextView(this)
        
        // Generate shared key (in production, exchange securely)
        sharedKey = ByteArray(32)
        SecureRandom().nextBytes(sharedKey!!)
        
        // Display IP address
        val ipAddress = getLocalIpAddress()
        ipAddressText.text = "Your IP: $ipAddress"
        statusText.text = "Your IP: $ipAddress\nClick 'Start Server' to accept connections"
        
        // Setup UI handlers
        startServerButton.text = "Start Server"
        startServerButton.setOnClickListener {
            if (isServerRunning) {
                stopServer()
            } else {
                startServer()
            }
        }
        
        sendButton.setOnClickListener {
            sendMessage()
        }
    }
    
    private fun getLocalIpAddress(): String {
        try {
            val interfaces = java.net.NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val networkInterface = interfaces.nextElement()
                val addresses = networkInterface.inetAddresses
                while (addresses.hasMoreElements()) {
                    val address = addresses.nextElement()
                    if (!address.isLoopbackAddress && address is java.net.Inet4Address) {
                        return address.hostAddress ?: "Unknown"
                    }
                }
            }
        } catch (e: Exception) {
            e.printStackTrace()
        }
        return "Unknown"
    }
    
    private fun startServer() {
        if (isServerRunning) return
        
        serverThread = Thread {
            try {
                val serverSocket = ServerSocket(8888)
                isServerRunning = true
                
                runOnUiThread {
                    statusText.text = "Server started. Waiting for connection on port 8888..."
                    startServerButton.text = "Stop Server"
                }
                
                // Accept connection
                val clientSocket = serverSocket.accept()
                serverSocket.close()
                
                runOnUiThread {
                    statusText.text = "Client connected!"
                }
                
                // Initialize TauSync with the connected socket
                initializeTauSync(clientSocket)
                
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "Server error: ${e.message}"
                    isServerRunning = false
                    startServerButton.text = "Start Server"
                }
            }
        }
        serverThread?.start()
    }
    
    private fun stopServer() {
        isServerRunning = false
        serverThread?.interrupt()
        transport?.let {
            (it as? SocketTransport)?.disconnect()
        }
        runOnUiThread {
            statusText.text = "Server stopped"
            startServerButton.text = "Start Server"
        }
    }
    
    private fun initializeTauSync(clientSocket: java.net.Socket) {
        // Create secure channel
        secureChannel = SecureChannel()
        secureChannel?.initialize(sharedKey!!)
        
        // Create socket transport (we'll need to modify SocketTransport to accept existing socket)
        // For now, we'll create a new one and connect
        transport = SocketTransport()
        (transport as SocketTransport).port = 8888
        
        // Create connection manager
        connectionManager = ConnectionManager()
        connectionManager?.initialize(transport!!, secureChannel!!)
        
        // Set up listeners
        connectionManager?.setRequestReceivedListener { req ->
            runOnUiThread {
                val message = String(req.payload, StandardCharsets.UTF_8)
                receivedText.append("Received: $message\n")
            }
        }
        
        connectionManager?.setErrorOccurredListener { ex ->
            runOnUiThread {
                statusText.text = "Error: ${ex.message}"
            }
        }
        
        runOnUiThread {
            statusText.text = "TauSync ready! You can send messages now."
        }
    }
    
    private fun sendMessage() {
        val message = messageInput.text.toString()
        if (message.isEmpty()) {
            return
        }
        
        Thread {
            try {
                if (transport == null || !transport!!.isConnected) {
                    runOnUiThread {
                        statusText.text = "Not connected. Please start server first."
                    }
                    return@Thread
                }
                
                val request = TransferRequest()
                request.payload = message.toByteArray(StandardCharsets.UTF_8)
                request.priority = 0
                request.isCompressed = false
                request.cryptoIV = ByteArray(0) // Will be generated automatically
                
                connectionManager?.smartSend(request)
                
                runOnUiThread {
                    messageInput.text.clear()
                    statusText.text = "Message sent: $message"
                }
            } catch (e: Exception) {
                runOnUiThread {
                    statusText.text = "Send error: ${e.message}"
                }
            }
        }.start()
    }
    
    override fun onDestroy() {
        super.onDestroy()
        stopServer()
    }
}
