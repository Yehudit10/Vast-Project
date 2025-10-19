// let currentClientId = null
// let currentEditId = null
// const apiUrl = "http://127.0.0.1:5000"

// document.addEventListener("DOMContentLoaded", () => {
//   console.log("[v0] DOM loaded, initializing...")

//   // Get elements
//   const continueBtn = document.getElementById("continueBtn")
//   const changeClientBtn = document.getElementById("changeClientBtn")
//   const saveBtn = document.getElementById("saveBtn")
//   const cancelBtn = document.getElementById("cancelBtn")
//   const loadEditBtn = document.getElementById("loadEditBtn")
//   const deleteBtn = document.getElementById("deleteBtn")
//   const closeBtn = document.getElementById("closeBtn")

//   // Add event listeners
//   if (continueBtn) {
//     continueBtn.addEventListener("click", setClientId)
//   }
//   if (changeClientBtn) {
//     changeClientBtn.addEventListener("click", showClientIdScreen)
//   }
//   if (saveBtn) {
//     saveBtn.addEventListener("click", saveNotification)
//   }
//   if (cancelBtn) {
//     cancelBtn.addEventListener("click", resetForm)
//   }
//   if (loadEditBtn) {
//     loadEditBtn.addEventListener("click", loadForEdit)
//   }
//   if (deleteBtn) {
//     deleteBtn.addEventListener("click", deleteNotification)
//   }
//   if (closeBtn) {
//     closeBtn.addEventListener("click", closePopup)
//   }

//   // Tab switching
//   const tabBtns = document.querySelectorAll(".tab-btn")
//   tabBtns.forEach((btn) => {
//     btn.addEventListener("click", () => switchTab(btn.dataset.tab))
//   })

//   console.log("[v0] Event listeners attached")
// })

// function setClientId() {
//   const clientIdInput = document.getElementById("userClientId")
//   const clientId = clientIdInput.value.trim()

//   if (!clientId) {
//     showStatus("Please enter a valid Client ID", "error")
//     return
//   }

//   currentClientId = Number.parseInt(clientId)
//   document.getElementById("currentClientId").textContent = currentClientId

//   // Show main screen
//   document.getElementById("clientIdScreen").classList.remove("active")
//   document.getElementById("mainScreen").classList.add("active")

//   console.log("[v0] Client ID set to:", currentClientId)
// }

// function showClientIdScreen() {
//   document.getElementById("clientIdScreen").classList.add("active")
//   document.getElementById("mainScreen").classList.remove("active")
//   document.getElementById("userClientId").focus()
// }

// function switchTab(tabName) {
//   // Remove active from all tabs
//   document.querySelectorAll(".tab-btn").forEach((btn) => btn.classList.remove("active"))
//   document.querySelectorAll(".tab-content").forEach((content) => content.classList.remove("active"))

//   // Add active to selected tab
//   document.querySelector(`[data-tab="${tabName}"]`).classList.add("active")
//   document.getElementById(`${tabName}Tab`).classList.add("active")

//   if (tabName === "add") {
//     resetForm()
//   }
// }

// function resetForm() {
//   currentEditId = null
//   document.getElementById("formTitle").textContent = "Add New Notification"
//   document.getElementById("team").value = ""
//   document.getElementById("notificationTime").value = "09:00"
//   document.getElementById("startTime").value = "08:00"
//   document.getElementById("endTime").value = "17:00"

//   // Reset checkboxes
//   const checkboxes = document.querySelectorAll('.checkbox-group input[type="checkbox"]')
//   checkboxes.forEach((checkbox) => {
//     checkbox.checked = checkbox.value === "Monday" || checkbox.value === "Friday"
//   })
// }

// async function loadForEdit() {
//   const scheduleId = document.getElementById("editScheduleId").value.trim()
//   if (!scheduleId) {
//     showStatus("Please enter a Schedule ID", "error")
//     return
//   }

//   showStatus("Loading notification...", "loading")

//   try {
//     const response = await fetch(`${apiUrl}/schedule/${scheduleId}`)

//     if (response.ok) {
//       const schedule = await response.json()

//       if (schedule.client_id !== currentClientId) {
//         showStatus(`Schedule ID ${scheduleId} does not belong to client ${currentClientId}`, "error")
//         return
//       }

//       // Fill form with data
//       currentEditId = Number.parseInt(scheduleId)
//       document.getElementById("formTitle").textContent = `Edit Notification (ID: ${scheduleId})`
//       document.getElementById("team").value = schedule.team

//       // Parse time from cron
//       const cronParts = schedule.cron_expr.split(" ")
//       const hour = cronParts[1].padStart(2, "0")
//       const minute = cronParts[0].padStart(2, "0")
//       document.getElementById("notificationTime").value = `${hour}:${minute}`

//       // Parse time window
//       const timeWindow = schedule.time_window.split("-")
//       document.getElementById("startTime").value = timeWindow[0]
//       document.getElementById("endTime").value = timeWindow[1]

//       // Set active days
//       const activeDays = schedule.active_days.split(", ")
//       const checkboxes = document.querySelectorAll('.checkbox-group input[type="checkbox"]')
//       checkboxes.forEach((checkbox) => {
//         checkbox.checked = activeDays.includes(checkbox.value)
//       })

//       // Switch to add tab for editing
//       switchTab("add")
//       showStatus("Notification loaded for editing", "success")
//     } else {
//       const result = await response.json()
//       showStatus(`Error: ${result.error || "Failed to load"}`, "error")
//     }
//   } catch (error) {
//     console.error("Error loading notification:", error)
//     showStatus("Error connecting to server", "error")
//   }
// }

// async function deleteNotification() {
//   const scheduleId = document.getElementById("deleteScheduleId").value.trim()
//   if (!scheduleId) {
//     showStatus("Please enter a Schedule ID", "error")
//     return
//   }

//   if (!confirm(`Are you sure you want to delete notification with Schedule ID: ${scheduleId}?`)) {
//     return
//   }

//   showStatus("Deleting notification...", "loading")

//   try {
//     const response = await fetch(`${apiUrl}/schedule/${scheduleId}`, {
//       method: "DELETE",
//     })

//     if (response.ok) {
//       showStatus("Notification deleted successfully", "success")
//       document.getElementById("deleteScheduleId").value = ""
//     } else {
//       const result = await response.json()
//       showStatus(`Error: ${result.error || "Failed to delete"}`, "error")
//     }
//   } catch (error) {
//     console.error("Error deleting notification:", error)
//     showStatus("Error connecting to server", "error")
//   }
// }

// async function saveNotification() {
//   const team = document.getElementById("team").value
//   if (!team) {
//     showStatus("Please select a team", "error")
//     return
//   }

//   const selectedDays = getSelectedDays()
//   if (!selectedDays) {
//     showStatus("Please select at least one active day", "error")
//     return
//   }

//   showStatus(currentEditId ? "Updating notification..." : "Saving notification...", "loading")

//   const notificationData = {
//     client_id: currentClientId,
//     team: team,
//     cron_expr: generateCronExpression(),
//     active_days: selectedDays,
//     time_window: getTimeWindow(),
//   }

//   try {
//     const url = currentEditId ? `${apiUrl}/schedule/${currentEditId}` : `${apiUrl}/schedule`
//     const method = currentEditId ? "PUT" : "POST"

//     const response = await fetch(url, {
//       method: method,
//       headers: {
//         "Content-Type": "application/json",
//       },
//       body: JSON.stringify(notificationData),
//     })

//     if (response.ok) {
//       const result = await response.json()
//       const action = currentEditId ? "updated" : "saved"

//       if (!currentEditId && result.schedule_id) {
//         showStatus(`Notification ${action} successfully! Schedule ID: ${result.schedule_id}`, "success")
//       } else {
//         showStatus(`Notification ${action} successfully!`, "success")
//       }

//       resetForm()
//     } else {
//       const result = await response.json()
//       showStatus(`Error: ${result.error || "Failed to save"}`, "error")
//     }
//   } catch (error) {
//     console.error("Error saving notification:", error)
//     showStatus("Error connecting to server", "error")
//   }
// }

// function getSelectedDays() {
//   const selectedDays = []
//   const checkboxes = document.querySelectorAll('.checkbox-group input[type="checkbox"]')
//   checkboxes.forEach((checkbox) => {
//     if (checkbox.checked) {
//       selectedDays.push(checkbox.value)
//     }
//   })
//   return selectedDays.join(", ")
// }

// function generateCronExpression() {
//   const time = document.getElementById("notificationTime").value.split(":")
//   const hour = Number.parseInt(time[0])
//   const minute = Number.parseInt(time[1])
//   return `${minute} ${hour} * * *`
// }

// function getTimeWindow() {
//   const startTime = document.getElementById("startTime").value
//   const endTime = document.getElementById("endTime").value
//   return `${startTime}-${endTime}`
// }

// function showStatus(message, type) {
//   const statusMessage = document.getElementById("statusMessage")
//   statusMessage.textContent = message
//   statusMessage.className = `status-message ${type}`
//   statusMessage.style.display = "block"

//   if (type === "success") {
//     setTimeout(() => {
//       statusMessage.style.display = "none"
//     }, 3000)
//   }
// }

// function closePopup() {
//   document.getElementById("popupOverlay").style.display = "none"
//   showClientIdScreen()
//   currentClientId = null
//   document.getElementById("userClientId").value = ""
// }

// // Global function to open popup
// window.openNotificationPopup = () => {
//   document.getElementById("popupOverlay").style.display = "flex"
// }

class NotificationManager {
  constructor() {
    this.apiUrl = "http://127.0.0.1:5000"
    this.currentEditId = null
    this.currentClientId = null
    this.initializeElements()
    this.attachEventListeners()
  }

  initializeElements() {
    this.popup = document.getElementById("popupOverlay")
    this.closeBtn = document.getElementById("closeBtn")
    this.cancelBtn = document.getElementById("cancelBtn")
    this.saveBtn = document.getElementById("saveBtn")
    this.statusMessage = document.getElementById("statusMessage")
    this.formTitle = document.getElementById("formTitle")

    this.teamSelect = document.getElementById("team")
    this.notificationTimeInput = document.getElementById("notificationTime")
    this.startTimeInput = document.getElementById("startTime")
    this.endTimeInput = document.getElementById("endTime")
    this.checkboxes = document.querySelectorAll('.checkbox-group input[type="checkbox"]')

    this.tabBtns = document.querySelectorAll(".tab-btn")
    this.tabContents = document.querySelectorAll(".tab-content")

    this.userClientIdInput = document.getElementById("userClientId")
    this.continueBtn = document.getElementById("continueBtn")
    this.changeClientBtn = document.getElementById("changeClientBtn")
    this.currentClientIdSpan = document.getElementById("currentClientId")

    this.clientIdScreen = document.getElementById("clientIdScreen")
    this.mainScreen = document.getElementById("mainScreen")

    // Refresh button and notifications list
    this.refreshBtn = document.getElementById("refreshBtn")
    this.notificationsList = document.getElementById("notificationsList")
  }

  attachEventListeners() {
    if (this.closeBtn) this.closeBtn.addEventListener("click", () => this.closePopup())
    if (this.cancelBtn) this.cancelBtn.addEventListener("click", () => this.cancelForm())
    if (this.saveBtn) this.saveBtn.addEventListener("click", () => this.saveNotification())

    if (this.continueBtn) this.continueBtn.addEventListener("click", () => this.setClientId())
    if (this.changeClientBtn) this.changeClientBtn.addEventListener("click", () => this.showClientIdScreen())

    // Add refresh button listener
    if (this.refreshBtn) this.refreshBtn.addEventListener("click", () => this.loadNotifications())

    // Tab switching
    this.tabBtns.forEach((btn) => {
      btn.addEventListener("click", () => this.switchTab(btn.dataset.tab))
    })

    // Close popup when clicking outside
    if (this.popup) {
      this.popup.addEventListener("click", (e) => {
        if (e.target === this.popup) {
          this.closePopup()
        }
      })
    }

    // Close popup with Escape key
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        this.closePopup()
      }
    })

    if (this.userClientIdInput) {
      this.userClientIdInput.addEventListener("keypress", (e) => {
        if (e.key === "Enter") {
          this.setClientId()
        }
      })
    }
  }

  setClientId() {
    const clientId = this.userClientIdInput.value.trim()
    if (!clientId) {
      this.showStatus("Please enter a valid Client ID", "error")
      return
    }

    this.currentClientId = Number.parseInt(clientId)
    this.currentClientIdSpan.textContent = this.currentClientId
    this.showMainScreen()
    // Load notifications when entering new client
    this.loadNotifications()
  }

  showClientIdScreen() {
    this.clientIdScreen.classList.add("active")
    this.mainScreen.classList.remove("active")
    this.userClientIdInput.focus()
  }

  showMainScreen() {
    this.clientIdScreen.classList.remove("active")
    this.mainScreen.classList.add("active")
  }

  switchTab(tabName) {
    this.tabBtns.forEach((btn) => btn.classList.remove("active"))
    this.tabContents.forEach((content) => content.classList.remove("active"))

    document.querySelector(`[data-tab="${tabName}"]`).classList.add("active")
    document.getElementById(`${tabName}Tab`).classList.add("active")

    if (tabName === "add") {
      // Only reset form if we're not editing
      if (!this.currentEditId) {
        this.resetForm()
      }
    } else if (tabName === "list") {
      // Load notifications when switching to list tab
      this.loadNotifications()
    }
  }

  // Load all notifications for current client
  async loadNotifications() {
    if (!this.currentClientId) {
      console.log("No current client ID")
      return
    }

    console.log(`[v0] Loading notifications for client ${this.currentClientId}`)
    this.notificationsList.innerHTML = '<div class="loading-message">Loading notifications...</div>'

    try {
      const response = await fetch(`${this.apiUrl}/schedules?client_id=${this.currentClientId}`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      })

      console.log(`[v0] Response status: ${response.status}`)

      if (response.ok) {
        const schedules = await response.json()
        console.log("[v0] Loaded data:", schedules)
        this.displayNotifications(schedules)
      } else {
        const error = await response.json()
        console.log("[v0] Error response:", error)
        this.notificationsList.innerHTML = `<div class="empty-message">Error loading data: ${error.error || "Unknown error"}</div>`
      }
    } catch (error) {
      console.error("[v0] Network error:", error)
      this.notificationsList.innerHTML = '<div class="empty-message">Error connecting to server. Check that server is running on port 5000</div>'
    }
  }

  // Display notifications in the list
  displayNotifications(schedules) {
    if (!schedules || schedules.length === 0) {
      this.notificationsList.innerHTML = '<div class="empty-message">No notifications for this client</div>'
      return
    }

    const notificationsHtml = schedules.map(schedule => `
      <div class="notification-item">
        <div class="notification-header">
          <div class="notification-title">${schedule.team} Team</div>
          <div class="notification-actions">
            <button class="btn btn-edit" onclick="notificationManager.editNotification(${schedule.schedule_id})">Edit</button>
            <button class="btn btn-delete" onclick="notificationManager.deleteNotification(${schedule.schedule_id})">Delete</button>
          </div>
        </div>
        <div class="notification-details">
          <div><strong>Schedule ID:</strong> ${schedule.schedule_id}</div>
          <div><strong>Notification Time:</strong> ${this.formatCronTime(schedule.cron_expr)}</div>
          <div><strong>Active Days:</strong> ${schedule.active_days}</div>
          <div><strong>Time Window:</strong> ${schedule.time_window}</div>
          <div><strong>Last Updated:</strong> ${this.formatDate(schedule.last_updated)}</div>
        </div>
      </div>
    `).join('')

    this.notificationsList.innerHTML = notificationsHtml
  }

  // Helper to format time from cron expression
  formatCronTime(cronExpr) {
    const parts = cronExpr.split(' ')
    if (parts.length >= 2) {
      const hour = parts[1].padStart(2, '0')
      const minute = parts[0].padStart(2, '0')
      return `${hour}:${minute}`
    }
    return cronExpr
  }

  // Helper to format date
  formatDate(dateStr) {
    if (!dateStr) return 'Unknown'
    return new Date(dateStr).toLocaleString('en-US')
  }

  // Edit notification from list - loads data and switches to add tab
  async editNotification(scheduleId) {
    console.log(`[v0] Editing notification ${scheduleId}`)
    this.showStatus("Loading notification for editing...", "loading")

    try {
      const response = await fetch(`${this.apiUrl}/schedule/${scheduleId}`, {
        method: "GET",
        headers: {
          "Content-Type": "application/json",
        },
      })

      console.log("[v0] Response status:", response.status)

      if (response.ok) {
        const schedule = await response.json()
        console.log("[v0] Loaded schedule data:", schedule)

        if (schedule.client_id !== this.currentClientId) {
          this.showStatus(`Schedule ID ${scheduleId} does not belong to client ${this.currentClientId}`, "error")
          return
        }

        // Set edit mode
        this.currentEditId = Number.parseInt(scheduleId)
        this.formTitle.textContent = `Edit Notification (Schedule ID: ${scheduleId})`

        // Update the tab button title for "Add New" to "Edit"
        const addTabBtn = document.querySelector('button[data-tab="add"]');
        addTabBtn.textContent = "Edit Notification";

        // Fill form fields with existing data
        this.teamSelect.value = schedule.team

        // Parse cron expression to get time
        const cronParts = schedule.cron_expr.split(" ")
        const hour = cronParts[1].padStart(2, "0")
        const minute = cronParts[0].padStart(2, "0")
        this.notificationTimeInput.value = `${hour}:${minute}`

        // Parse time window
        const timeWindow = schedule.time_window.split("-")
        this.startTimeInput.value = timeWindow[0]
        this.endTimeInput.value = timeWindow[1]

        // Set active days checkboxes
        const activeDays = schedule.active_days.split(", ")
        this.checkboxes.forEach((checkbox) => {
          checkbox.checked = activeDays.includes(checkbox.value)
        })

        // Switch to add tab for editing
        this.switchTab("add")
        this.showStatus("Notification loaded for editing", "success")
      } else {
        const result = await response.json()
        console.log("[v0] Error response:", result)
        this.showStatus(`Error: ${result.error || "Failed to load"}`, "error")
      }
    } catch (error) {
      console.error("[v0] Error loading notification:", error)
      this.showStatus("Error connecting to server", "error")
    }
  }

  // Delete notification from list
  async deleteNotification(scheduleId) {
    if (!confirm(`Are you sure you want to delete notification with Schedule ID: ${scheduleId}?`)) {
      return
    }

    console.log(`[v0] Deleting notification ${scheduleId}`)
    this.showStatus("Deleting notification...", "loading")

    try {
      const response = await fetch(`${this.apiUrl}/schedule/${scheduleId}`, {
        method: "DELETE",
        headers: {
          "Content-Type": "application/json",
        },
      })

      if (response.ok) {
        this.showStatus("Notification deleted successfully", "success")
        this.loadNotifications() // Refresh the list
      } else {
        const result = await response.json()
        this.showStatus(`Error: ${result.error || "Failed to delete"}`, "error")
      }
    } catch (error) {
      console.error("Error deleting notification:", error)
      this.showStatus("Error connecting to server", "error")
    }
  }

  resetForm() {
    this.currentEditId = null
    this.formTitle.textContent = "Add New Notification"
    this.teamSelect.value = ""
    this.notificationTimeInput.value = "09:00"
    this.startTimeInput.value = "08:00"
    this.endTimeInput.value = "17:00"

    this.checkboxes.forEach((checkbox) => {
      checkbox.checked = checkbox.value === "Monday" || checkbox.value === "Friday"
    })
  }

  cancelForm() {
    this.resetForm()
    this.switchTab("list")
  }

  closePopup() {
    this.popup.style.display = "none"
    this.showClientIdScreen()
    this.currentClientId = null
    this.currentEditId = null
    this.userClientIdInput.value = ""
    if (window.parent && window.parent.closeNotificationPopup) {
      window.parent.closeNotificationPopup()
    }
  }

  validateForm() {
    if (!this.teamSelect.value) {
      this.showStatus("Please select a team", "error")
      return false
    }

    const selectedDays = this.getSelectedDays()
    if (!selectedDays) {
      this.showStatus("Please select at least one active day", "error")
      return false
    }

    return true
  }

  async saveNotification() {
    if (!this.validateForm()) {
      return
    }

    this.saveBtn.disabled = true
    this.showStatus(this.currentEditId ? "Updating notification..." : "Saving notification...", "loading")

    const notificationData = {
      client_id: this.currentClientId,
      team: this.teamSelect.value,
      cron_expr: this.generateCronExpression(),
      active_days: this.getSelectedDays(),
      time_window: this.getTimeWindow(),
    }

    try {
      const url = this.currentEditId ? `${this.apiUrl}/schedule/${this.currentEditId}` : `${this.apiUrl}/schedule`
      const method = this.currentEditId ? "PUT" : "POST"

      const response = await fetch(url, {
        method: method,
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(notificationData),
      })

      if (response.ok) {
        const result = await response.json()
        const action = this.currentEditId ? "updated" : "saved"
        this.showStatus(`Notification ${action} successfully!`, "success")

        if (!this.currentEditId && result.schedule_id) {
          this.showStatus(`Notification saved successfully! Schedule ID: ${result.schedule_id}`, "success")
        }

        this.resetForm()
        // Refresh the list and go back to list tab
        this.loadNotifications()
        this.switchTab("list")
      } else {
        let errorMessage = "Unknown error occurred"
        try {
          const result = await response.json()
          errorMessage = result.error || result.message || errorMessage
        } catch (e) {
          errorMessage = `Server error: ${response.status} ${response.statusText}`
        }
        this.showStatus(`Error: ${errorMessage}`, "error")
      }
    } catch (error) {
      console.error("Network error:", error)
      this.showStatus("Network error. Please check if the server is running.", "error")
    } finally {
      this.saveBtn.disabled = false
    }
  }

  getSelectedDays() {
    const selectedDays = []
    this.checkboxes.forEach((checkbox) => {
      if (checkbox.checked) {
        selectedDays.push(checkbox.value)
      }
    })
    return selectedDays.join(", ")
  }

  generateCronExpression() {
    const time = this.notificationTimeInput.value.split(":")
    const hour = Number.parseInt(time[0])
    const minute = Number.parseInt(time[1])
    return `${minute} ${hour} * * *`
  }

  getTimeWindow() {
    return `${this.startTimeInput.value}-${this.endTimeInput.value}`
  }

  showStatus(message, type) {
    this.statusMessage.textContent = message
    this.statusMessage.className = `status-message ${type}`
    this.statusMessage.style.display = "block"

    if (type === "success") {
      setTimeout(() => {
        this.statusMessage.style.display = "none"
      }, 3000)
    }
  }
}

// Initialize notification manager when page loads
let notificationManager
document.addEventListener("DOMContentLoaded", () => {
  notificationManager = new NotificationManager()
})

// Global function to open popup
window.openNotificationPopup = () => {
  document.getElementById("popupOverlay").style.display = "flex"
}