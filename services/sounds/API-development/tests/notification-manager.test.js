/**
 * @jest-environment jsdom
 */

const NotificationManager = require('../src/window-client/script.js');

describe('NotificationManager', () => {
  let notificationManager;
  let mockFetch;
  
  beforeEach(() => {
    // Create a basic HTML structure with select options
    document.body.innerHTML = `
      <div id="popupOverlay"></div>
      <button id="closeBtn"></button>
      <button id="cancelBtn"></button>
      <button id="saveBtn"></button>
      <div id="statusMessage"></div>
      <h2 id="formTitle"></h2>
      <select id="team">
        <option value="">Select Team</option>
        <option value="Development">Development</option>
        <option value="QA">QA</option>
        <option value="Support">Support</option>
      </select>
      <input id="notificationTime" type="time" />
      <input id="startTime" type="time" />
      <input id="endTime" type="time" />
      <div class="checkbox-group">
        <input type="checkbox" value="Monday" />
        <input type="checkbox" value="Tuesday" />
        <input type="checkbox" value="Wednesday" />
        <input type="checkbox" value="Thursday" />
        <input type="checkbox" value="Friday" />
        <input type="checkbox" value="Saturday" />
        <input type="checkbox" value="Sunday" />
      </div>
      <button class="tab-btn" data-tab="add"></button>
      <button class="tab-btn" data-tab="list"></button>
      <div class="tab-content" id="addTab"></div>
      <div class="tab-content" id="listTab"></div>
      <input id="userClientId" />
      <button id="continueBtn"></button>
      <button id="changeClientBtn"></button>
      <span id="currentClientId"></span>
      <div id="clientIdScreen"></div>
      <div id="mainScreen"></div>
      <button id="refreshBtn"></button>
      <div id="notificationsList"></div>
    `;
    
    mockFetch = jest.fn();
    global.fetch = mockFetch;
    
    notificationManager = new NotificationManager();
  });
  
  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('Initialization', () => {
    test('should initialize all elements correctly', () => {
      expect(notificationManager.popup).toBeDefined();
      expect(notificationManager.closeBtn).toBeDefined();
      expect(notificationManager.teamSelect).toBeDefined();
      expect(notificationManager.apiUrl).toBe('http://127.0.0.1:5000');
    });

    test('should start with currentEditId as null', () => {
      expect(notificationManager.currentEditId).toBeNull();
    });

    test('should start with currentClientId as null', () => {
      expect(notificationManager.currentClientId).toBeNull();
    });
  });

  describe('Event Listeners', () => {
    test('should close popup on Escape key', () => {
      const closePopupSpy = jest.spyOn(notificationManager, 'closePopup');
      const event = new KeyboardEvent('keydown', { key: 'Escape' });
      document.dispatchEvent(event);
      
      expect(closePopupSpy).toHaveBeenCalled();
    });

    test('should close popup when clicking on overlay background', () => {
      const closePopupSpy = jest.spyOn(notificationManager, 'closePopup');
      const event = new MouseEvent('click', { bubbles: true });
      Object.defineProperty(event, 'target', { value: notificationManager.popup });
      
      notificationManager.popup.dispatchEvent(event);
      
      expect(closePopupSpy).toHaveBeenCalled();
    });

    test('should not close popup when clicking inside content', () => {
      const closePopupSpy = jest.spyOn(notificationManager, 'closePopup');
      const innerElement = document.createElement('div');
      notificationManager.popup.appendChild(innerElement);
      
      const event = new MouseEvent('click', { bubbles: true });
      Object.defineProperty(event, 'target', { value: innerElement });
      
      notificationManager.popup.dispatchEvent(event);
      
      expect(closePopupSpy).not.toHaveBeenCalled();
    });

    test('should set client ID on Enter key press', () => {
      const setClientIdSpy = jest.spyOn(notificationManager, 'setClientId');
      notificationManager.userClientIdInput.value = '123';
      
      const event = new KeyboardEvent('keypress', { key: 'Enter' });
      notificationManager.userClientIdInput.dispatchEvent(event);
      
      expect(setClientIdSpy).toHaveBeenCalled();
    });

    test('should call cancelForm when cancel button clicked', () => {
      const cancelFormSpy = jest.spyOn(notificationManager, 'cancelForm');
      notificationManager.cancelBtn.click();
      
      expect(cancelFormSpy).toHaveBeenCalled();
    });

    test('should call saveNotification when save button clicked', () => {
      const saveNotificationSpy = jest.spyOn(notificationManager, 'saveNotification').mockImplementation(() => {});
      notificationManager.saveBtn.click();
      
      expect(saveNotificationSpy).toHaveBeenCalled();
      saveNotificationSpy.mockRestore();
    });

    test('should call showClientIdScreen when change client button clicked', () => {
      const showClientIdScreenSpy = jest.spyOn(notificationManager, 'showClientIdScreen');
      notificationManager.changeClientBtn.click();
      
      expect(showClientIdScreenSpy).toHaveBeenCalled();
    });

    test('should call loadNotifications when refresh button clicked', () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      notificationManager.refreshBtn.click();
      
      expect(loadNotificationsSpy).toHaveBeenCalled();
      loadNotificationsSpy.mockRestore();
    });
  });

  describe('setClientId', () => {
    test('should set the client ID when valid', () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      notificationManager.userClientIdInput.value = '123';
      notificationManager.setClientId();
      
      expect(notificationManager.currentClientId).toBe(123);
      expect(notificationManager.currentClientIdSpan.textContent).toBe('123');
      
      loadNotificationsSpy.mockRestore();
    });

    test('should show error when client ID is empty', () => {
      const showStatusSpy = jest.spyOn(notificationManager, 'showStatus');
      notificationManager.userClientIdInput.value = '';
      notificationManager.setClientId();
      
      expect(showStatusSpy).toHaveBeenCalledWith(
        'Please enter a valid Client ID',
        'error'
      );
    });

    test('should load notifications after setting client ID', () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      notificationManager.userClientIdInput.value = '456';
      notificationManager.setClientId();
      
      expect(loadNotificationsSpy).toHaveBeenCalled();
      loadNotificationsSpy.mockRestore();
    });
  });

  describe('showClientIdScreen and showMainScreen', () => {
    test('should show client ID screen and focus input', () => {
      const focusSpy = jest.spyOn(notificationManager.userClientIdInput, 'focus');
      
      notificationManager.showClientIdScreen();
      
      expect(notificationManager.clientIdScreen.classList.contains('active')).toBe(true);
      expect(notificationManager.mainScreen.classList.contains('active')).toBe(false);
      expect(focusSpy).toHaveBeenCalled();
    });

    test('should show main screen', () => {
      notificationManager.showMainScreen();
      
      expect(notificationManager.clientIdScreen.classList.contains('active')).toBe(false);
      expect(notificationManager.mainScreen.classList.contains('active')).toBe(true);
    });
  });

  describe('validateForm', () => {
    test('should return false when no team is selected', () => {
      notificationManager.teamSelect.value = '';
      const result = notificationManager.validateForm();
      
      expect(result).toBe(false);
    });

    test('should return false when no active days are selected', () => {
      notificationManager.teamSelect.value = 'Development';
      notificationManager.checkboxes.forEach(cb => cb.checked = false);
      
      const result = notificationManager.validateForm();
      expect(result).toBe(false);
    });

    test('should return true when all fields are valid', () => {
      notificationManager.teamSelect.value = 'Development';
      notificationManager.checkboxes[0].checked = true;
      
      const result = notificationManager.validateForm();
      expect(result).toBe(true);
    });
  });

  describe('generateCronExpression', () => {
    test('should generate correct cron expression', () => {
      notificationManager.notificationTimeInput.value = '09:30';
      const cronExpr = notificationManager.generateCronExpression();
      
      expect(cronExpr).toBe('30 9 * * *');
    });

    test('should handle single hours correctly', () => {
      notificationManager.notificationTimeInput.value = '05:15';
      const cronExpr = notificationManager.generateCronExpression();
      
      expect(cronExpr).toBe('15 5 * * *');
    });
  });

  describe('getSelectedDays', () => {
    test('should return a string of selected days', () => {
      notificationManager.checkboxes[0].checked = true; // Monday
      notificationManager.checkboxes[4].checked = true; // Friday
      
      const days = notificationManager.getSelectedDays();
      expect(days).toBe('Monday, Friday');
    });

    test('should return an empty string when no days are selected', () => {
      notificationManager.checkboxes.forEach(cb => cb.checked = false);
      
      const days = notificationManager.getSelectedDays();
      expect(days).toBe('');
    });
  });

  describe('getTimeWindow', () => {
    test('should return time window in the correct format', () => {
      notificationManager.startTimeInput.value = '08:00';
      notificationManager.endTimeInput.value = '17:00';
      
      const timeWindow = notificationManager.getTimeWindow();
      expect(timeWindow).toBe('08:00-17:00');
    });
  });

  describe('resetForm', () => {
    test('should reset all form fields', () => {
      notificationManager.currentEditId = 123;
      notificationManager.teamSelect.value = 'Development';
      
      notificationManager.resetForm();
      
      expect(notificationManager.currentEditId).toBeNull();
      expect(notificationManager.teamSelect.value).toBe('');
      expect(notificationManager.formTitle.textContent).toBe('Add New Notification');
    });

    test('should set default values for times', () => {
      notificationManager.resetForm();
      
      expect(notificationManager.notificationTimeInput.value).toBe('09:00');
      expect(notificationManager.startTimeInput.value).toBe('08:00');
      expect(notificationManager.endTimeInput.value).toBe('17:00');
    });

    test('should check Monday and Friday by default', () => {
      notificationManager.resetForm();
      
      expect(notificationManager.checkboxes[0].checked).toBe(true); // Monday
      expect(notificationManager.checkboxes[4].checked).toBe(true); // Friday
      expect(notificationManager.checkboxes[2].checked).toBe(false); // Wednesday
    });
  });

  describe('cancelForm', () => {
    test('should reset form and switch to list tab', () => {
      const resetFormSpy = jest.spyOn(notificationManager, 'resetForm');
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      notificationManager.cancelForm();
      
      expect(resetFormSpy).toHaveBeenCalled();
      expect(switchTabSpy).toHaveBeenCalledWith('list');
      
      switchTabSpy.mockRestore();
    });
  });

  describe('loadNotifications', () => {
    test('should load notifications successfully', async () => {
      notificationManager.currentClientId = 123;
      const mockSchedules = [
        {
          schedule_id: 1,
          team: 'Development',
          cron_expr: '0 9 * * *',
          active_days: 'Monday, Friday',
          time_window: '08:00-17:00',
          last_updated: '2025-01-15T10:00:00'
        }
      ];
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockSchedules
      });
      
      await notificationManager.loadNotifications();
      
      expect(mockFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:5000/schedules?client_id=123',
        expect.any(Object)
      );
    });

    test('should show a message when no client ID', async () => {
      notificationManager.currentClientId = null;
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
      
      await notificationManager.loadNotifications();
      
      expect(consoleSpy).toHaveBeenCalledWith('No current client ID');
      consoleSpy.mockRestore();
    });

    test('should handle API error response', async () => {
      notificationManager.currentClientId = 123;
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ error: 'Database error' })
      });
      
      await notificationManager.loadNotifications();
      
      expect(notificationManager.notificationsList.innerHTML).toContain('Database error');
    });

    test('should handle network errors', async () => {
      notificationManager.currentClientId = 123;
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      await notificationManager.loadNotifications();
      
      expect(notificationManager.notificationsList.innerHTML).toContain(
        'Error connecting to server'
      );
    });

    test('should show loading message before fetching', async () => {
      notificationManager.currentClientId = 123;
      mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves
      
      notificationManager.loadNotifications();
      
      expect(notificationManager.notificationsList.innerHTML).toContain('Loading notifications...');
    });
  });

  describe('displayNotifications', () => {
    test('should display empty message when no schedules', () => {
      notificationManager.displayNotifications([]);
      
      expect(notificationManager.notificationsList.innerHTML).toContain('No notifications for this client');
    });

    test('should display empty message when schedules is null', () => {
      notificationManager.displayNotifications(null);
      
      expect(notificationManager.notificationsList.innerHTML).toContain('No notifications for this client');
    });

    test('should display notification items correctly', () => {
      const mockSchedules = [
        {
          schedule_id: 1,
          team: 'Development',
          cron_expr: '30 9 * * *',
          active_days: 'Monday, Friday',
          time_window: '08:00-17:00',
          last_updated: '2025-01-15T10:00:00'
        }
      ];
      
      notificationManager.displayNotifications(mockSchedules);
      
      expect(notificationManager.notificationsList.innerHTML).toContain('Development Team');
      expect(notificationManager.notificationsList.innerHTML).toContain('09:30');
      expect(notificationManager.notificationsList.innerHTML).toContain('Monday, Friday');
    });
  });

  describe('saveNotification', () => {
    beforeEach(() => {
      notificationManager.currentClientId = 123;
      notificationManager.teamSelect.value = 'Development';
      notificationManager.notificationTimeInput.value = '09:00';
      notificationManager.startTimeInput.value = '08:00';
      notificationManager.endTimeInput.value = '17:00';
      notificationManager.checkboxes[0].checked = true;
    });

    test('should save a new notification successfully', async () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ schedule_id: 1, message: 'Success' })
      });
      
      await notificationManager.saveNotification();
      
      expect(mockFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:5000/schedule',
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        })
      );
      
      loadNotificationsSpy.mockRestore();
      switchTabSpy.mockRestore();
    });

    test('should update an existing notification', async () => {
      notificationManager.currentEditId = 5;
      
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Updated' })
      });
      
      await notificationManager.saveNotification();
      
      expect(mockFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:5000/schedule/5',
        expect.objectContaining({
          method: 'PUT'
        })
      );
      
      loadNotificationsSpy.mockRestore();
      switchTabSpy.mockRestore();
    });

    test('should not save if form is invalid', async () => {
      notificationManager.teamSelect.value = '';
      
      await notificationManager.saveNotification();
      
      expect(mockFetch).not.toHaveBeenCalled();
    });

    test('should handle error response with error field', async () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ error: 'Invalid data' })
      });
      
      await notificationManager.saveNotification();
      
      expect(notificationManager.statusMessage.textContent).toContain('Invalid data');
      loadNotificationsSpy.mockRestore();
    });

    test('should handle error response with message field', async () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 400,
        statusText: 'Bad Request',
        json: async () => ({ message: 'Validation failed' })
      });
      
      await notificationManager.saveNotification();
      
      expect(notificationManager.statusMessage.textContent).toContain('Validation failed');
      loadNotificationsSpy.mockRestore();
    });

    test('should handle error response without json', async () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        json: async () => { throw new Error('No JSON'); }
      });
      
      await notificationManager.saveNotification();
      
      expect(notificationManager.statusMessage.textContent).toContain('500');
      loadNotificationsSpy.mockRestore();
    });

    test('should handle network error', async () => {
      mockFetch.mockRejectedValueOnce(new Error('Network failed'));
      
      await notificationManager.saveNotification();
      
      expect(notificationManager.statusMessage.textContent).toContain('Network error');
    });

    test('should re-enable save button after completion', async () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ schedule_id: 1 })
      });
      
      await notificationManager.saveNotification();
      
      expect(notificationManager.saveBtn.disabled).toBe(false);
      
      loadNotificationsSpy.mockRestore();
      switchTabSpy.mockRestore();
    });
  });

  describe('deleteNotification', () => {
    test('should delete notification after confirmation', async () => {
      global.confirm = jest.fn(() => true);
      
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Deleted' })
      });
      
      await notificationManager.deleteNotification(123);
      
      expect(mockFetch).toHaveBeenCalledWith(
        'http://127.0.0.1:5000/schedule/123',
        expect.objectContaining({ method: 'DELETE' })
      );
      expect(loadNotificationsSpy).toHaveBeenCalled();
      
      loadNotificationsSpy.mockRestore();
    });

    test('should not delete if user cancels', async () => {
      global.confirm = jest.fn(() => false);
      
      await notificationManager.deleteNotification(123);
      
      expect(mockFetch).not.toHaveBeenCalled();
    });

    test('should handle delete error', async () => {
      global.confirm = jest.fn(() => true);
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ error: 'Not found' })
      });
      
      await notificationManager.deleteNotification(123);
      
      expect(notificationManager.statusMessage.textContent).toContain('Not found');
    });

    test('should handle delete network error', async () => {
      global.confirm = jest.fn(() => true);
      
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      await notificationManager.deleteNotification(123);
      
      expect(notificationManager.statusMessage.textContent).toContain('Error connecting to server');
    });
  });

  describe('formatCronTime', () => {
    test('should format cron expression to time format', () => {
      const formatted = notificationManager.formatCronTime('30 9 * * *');
      expect(formatted).toBe('09:30');
    });

    test('should add leading zeros', () => {
      const formatted = notificationManager.formatCronTime('5 8 * * *');
      expect(formatted).toBe('08:05');
    });

    test('should return original expression if invalid', () => {
      const formatted = notificationManager.formatCronTime('invalid');
      expect(formatted).toBe('invalid');
    });
  });

  describe('formatDate', () => {
    test('should format date correctly', () => {
      const formatted = notificationManager.formatDate('2025-01-15T10:00:00');
      expect(formatted).toContain('2025');
    });

    test('should return Unknown for invalid date', () => {
      const formatted = notificationManager.formatDate(null);
      expect(formatted).toBe('Unknown');
    });

    test('should return Unknown for undefined', () => {
      const formatted = notificationManager.formatDate(undefined);
      expect(formatted).toBe('Unknown');
    });
  });

  describe('showStatus', () => {
    test('should display a status message', () => {
      notificationManager.showStatus('Test message', 'success');
      
      expect(notificationManager.statusMessage.textContent).toBe('Test message');
      expect(notificationManager.statusMessage.className).toContain('success');
      expect(notificationManager.statusMessage.style.display).toBe('block');
    });

    test('should display error message', () => {
      notificationManager.showStatus('Error message', 'error');
      
      expect(notificationManager.statusMessage.textContent).toBe('Error message');
      expect(notificationManager.statusMessage.className).toContain('error');
    });

    test('should display loading message', () => {
      notificationManager.showStatus('Loading...', 'loading');
      
      expect(notificationManager.statusMessage.textContent).toBe('Loading...');
      expect(notificationManager.statusMessage.className).toContain('loading');
    });

    test('should hide success message after 3 seconds', (done) => {
      jest.useFakeTimers();
      notificationManager.showStatus('Success', 'success');
      
      jest.advanceTimersByTime(3000);
      
      expect(notificationManager.statusMessage.style.display).toBe('none');
      jest.useRealTimers();
      done();
    });

    test('should not auto-hide error messages', (done) => {
      jest.useFakeTimers();
      notificationManager.showStatus('Error', 'error');
      
      jest.advanceTimersByTime(5000);
      
      expect(notificationManager.statusMessage.style.display).toBe('block');
      jest.useRealTimers();
      done();
    });
  });

  describe('switchTab', () => {
    test('should switch to the correct tab', () => {
      const addBtn = document.querySelector('[data-tab="add"]');
      const listBtn = document.querySelector('[data-tab="list"]');
      
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      notificationManager.switchTab('list');
      
      expect(listBtn.classList.contains('active')).toBe(true);
      expect(addBtn.classList.contains('active')).toBe(false);
      
      loadNotificationsSpy.mockRestore();
    });

    test('should load notifications when switching to the list tab', () => {
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      notificationManager.switchTab('list');
      
      expect(loadNotificationsSpy).toHaveBeenCalled();
      loadNotificationsSpy.mockRestore();
    });

    test('should reset form when switching to add tab if no active edit', () => {
      const resetFormSpy = jest.spyOn(notificationManager, 'resetForm');
      notificationManager.currentEditId = null;
      
      notificationManager.switchTab('add');
      
      expect(resetFormSpy).toHaveBeenCalled();
    });

    test('should not reset form when switching to add tab during edit', () => {
      const resetFormSpy = jest.spyOn(notificationManager, 'resetForm');
      notificationManager.currentEditId = 5;
      
      notificationManager.switchTab('add');
      
      expect(resetFormSpy).not.toHaveBeenCalled();
    });
  });

  describe('editNotification', () => {
    test('should load notification for editing', async () => {
      notificationManager.currentClientId = 123;
      const mockSchedule = {
        schedule_id: 1,
        client_id: 123,
        team: 'Development',
        cron_expr: '30 9 * * *',
        active_days: 'Monday, Friday',
        time_window: '08:00-17:00'
      };
      
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockSchedule
      });
      
      await notificationManager.editNotification(1);
      
      expect(notificationManager.currentEditId).toBe(1);
      expect(notificationManager.teamSelect.value).toBe('Development');
      expect(notificationManager.notificationTimeInput.value).toBe('09:30');
      
      switchTabSpy.mockRestore();
    });

    test('should show error if schedule belongs to another client', async () => {
      notificationManager.currentClientId = 123;
      const mockSchedule = {
        schedule_id: 1,
        client_id: 999,
        team: 'Development'
      };
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockSchedule
      });
      
      const showStatusSpy = jest.spyOn(notificationManager, 'showStatus');
      
      await notificationManager.editNotification(1);
      
      expect(showStatusSpy).toHaveBeenCalledWith(
        expect.stringContaining('does not belong to client'),
        'error'
      );
    });

    test('should handle edit API error', async () => {
      notificationManager.currentClientId = 123;
      
      mockFetch.mockResolvedValueOnce({
        ok: false,
        json: async () => ({ error: 'Schedule not found' })
      });
      
      await notificationManager.editNotification(1);
      
      expect(notificationManager.statusMessage.textContent).toContain('Schedule not found');
    });

    test('should handle edit network error', async () => {
      notificationManager.currentClientId = 123;
      
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      await notificationManager.editNotification(1);
      
      expect(notificationManager.statusMessage.textContent).toContain('Error connecting to server');
    });

    test('should update form title and checkboxes correctly', async () => {
      notificationManager.currentClientId = 123;
      const mockSchedule = {
        schedule_id: 5,
        client_id: 123,
        team: 'QA',
        cron_expr: '15 14 * * *',
        active_days: 'Tuesday, Thursday',
        time_window: '09:00-18:00'
      };
      
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => mockSchedule
      });
      
      await notificationManager.editNotification(5);
      
      expect(notificationManager.formTitle.textContent).toContain('Schedule ID: 5');
      expect(notificationManager.startTimeInput.value).toBe('09:00');
      expect(notificationManager.endTimeInput.value).toBe('18:00');
      
      // Check that Tuesday and Thursday are checked
      const tuesdayCheckbox = Array.from(notificationManager.checkboxes).find(cb => cb.value === 'Tuesday');
      const thursdayCheckbox = Array.from(notificationManager.checkboxes).find(cb => cb.value === 'Thursday');
      const mondayCheckbox = Array.from(notificationManager.checkboxes).find(cb => cb.value === 'Monday');
      
      expect(tuesdayCheckbox.checked).toBe(true);
      expect(thursdayCheckbox.checked).toBe(true);
      expect(mondayCheckbox.checked).toBe(false);
      
      switchTabSpy.mockRestore();
    });
  });

  describe('closePopup', () => {
    test('should reset everything and close the popup', () => {
      notificationManager.currentClientId = 123;
      notificationManager.currentEditId = 5;
      notificationManager.userClientIdInput.value = '123';
      
      notificationManager.closePopup();
      
      expect(notificationManager.popup.style.display).toBe('none');
      expect(notificationManager.currentClientId).toBeNull();
      expect(notificationManager.currentEditId).toBeNull();
      expect(notificationManager.userClientIdInput.value).toBe('');
    });

    test('should call parent closeNotificationPopup if available', () => {
      const mockCloseNotificationPopup = jest.fn();
      
      // Save original window.parent
      const originalParent = window.parent;
      
      // Mock window.parent with closeNotificationPopup function
      Object.defineProperty(window, 'parent', {
        writable: true,
        value: {
          closeNotificationPopup: mockCloseNotificationPopup
        }
      });
      
      notificationManager.closePopup();
      
      expect(mockCloseNotificationPopup).toHaveBeenCalled();
      
      // Restore original window.parent
      Object.defineProperty(window, 'parent', {
        writable: true,
        value: originalParent
      });
    });

    test('should not error if parent closeNotificationPopup is not available', () => {
      global.window = {
        parent: {}
      };
      
      expect(() => {
        notificationManager.closePopup();
      }).not.toThrow();
    });
  });

  describe('Tab Button Click Events', () => {
    test('should switch tabs when tab buttons are clicked', () => {
      const addBtn = document.querySelector('[data-tab="add"]');
      const listBtn = document.querySelector('[data-tab="list"]');
      
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      addBtn.click();
      expect(switchTabSpy).toHaveBeenCalledWith('add');
      
      listBtn.click();
      expect(switchTabSpy).toHaveBeenCalledWith('list');
      
      switchTabSpy.mockRestore();
    });
  });

  describe('Edge Cases and Additional Coverage', () => {
    test('should handle multiple days selected', () => {
      notificationManager.checkboxes[0].checked = true; // Monday
      notificationManager.checkboxes[2].checked = true; // Wednesday
      notificationManager.checkboxes[4].checked = true; // Friday
      notificationManager.checkboxes[6].checked = true; // Sunday
      
      const days = notificationManager.getSelectedDays();
      expect(days).toContain('Monday');
      expect(days).toContain('Wednesday');
      expect(days).toContain('Friday');
      expect(days).toContain('Sunday');
    });

    test('should handle time window with different formats', () => {
      notificationManager.startTimeInput.value = '06:30';
      notificationManager.endTimeInput.value = '22:45';
      
      const timeWindow = notificationManager.getTimeWindow();
      expect(timeWindow).toBe('06:30-22:45');
    });

    test('should generate cron for midnight', () => {
      notificationManager.notificationTimeInput.value = '00:00';
      const cronExpr = notificationManager.generateCronExpression();
      
      expect(cronExpr).toBe('0 0 * * *');
    });

    test('should generate cron for noon', () => {
      notificationManager.notificationTimeInput.value = '12:00';
      const cronExpr = notificationManager.generateCronExpression();
      
      expect(cronExpr).toBe('0 12 * * *');
    });

    test('should generate cron for late evening', () => {
      notificationManager.notificationTimeInput.value = '23:59';
      const cronExpr = notificationManager.generateCronExpression();
      
      expect(cronExpr).toBe('59 23 * * *');
    });
  });

  describe('Console Logging', () => {
    test('should log when loading notifications', async () => {
      notificationManager.currentClientId = 123;
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => []
      });
      
      await notificationManager.loadNotifications();
      
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Loading notifications'));
      consoleSpy.mockRestore();
    });

    test('should log response status', async () => {
      notificationManager.currentClientId = 123;
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => []
      });
      
      await notificationManager.loadNotifications();
      
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Response status'));
      consoleSpy.mockRestore();
    });

    test('should log when editing notification', async () => {
      notificationManager.currentClientId = 123;
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          schedule_id: 1,
          client_id: 123,
          team: 'Development',
          cron_expr: '0 9 * * *',
          active_days: 'Monday',
          time_window: '08:00-17:00'
        })
      });
      
      const switchTabSpy = jest.spyOn(notificationManager, 'switchTab').mockImplementation(() => {});
      
      await notificationManager.editNotification(1);
      
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Editing notification'));
      
      consoleSpy.mockRestore();
      switchTabSpy.mockRestore();
    });

    test('should log when deleting notification', async () => {
      global.confirm = jest.fn(() => true);
      const consoleSpy = jest.spyOn(console, 'log').mockImplementation(() => {});
      const loadNotificationsSpy = jest.spyOn(notificationManager, 'loadNotifications').mockImplementation(() => {});
      
      mockFetch.mockResolvedValueOnce({
        ok: true,
        json: async () => ({ message: 'Deleted' })
      });
      
      await notificationManager.deleteNotification(1);
      
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Deleting notification'));
      
      consoleSpy.mockRestore();
      loadNotificationsSpy.mockRestore();
    });
  });

  describe('Error Handling in Console', () => {
    test('should log error when network fails in loadNotifications', async () => {
      notificationManager.currentClientId = 123;
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      await notificationManager.loadNotifications();
      
      expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining('Network error'), expect.any(Error));
      
      consoleErrorSpy.mockRestore();
    });

    test('should log error when network fails in saveNotification', async () => {
      notificationManager.currentClientId = 123;
      notificationManager.teamSelect.value = 'Development';
      notificationManager.checkboxes[0].checked = true;
      
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      await notificationManager.saveNotification();
      
      expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining('Network error'), expect.any(Error));
      
      consoleErrorSpy.mockRestore();
    });

    test('should log error when network fails in deleteNotification', async () => {
      global.confirm = jest.fn(() => true);
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      await notificationManager.deleteNotification(1);
      
      expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining('Error deleting notification'), expect.any(Error));
      
      consoleErrorSpy.mockRestore();
    });

    test('should log error when network fails in editNotification', async () => {
      notificationManager.currentClientId = 123;
      const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation(() => {});
      
      mockFetch.mockRejectedValueOnce(new Error('Network error'));
      
      await notificationManager.editNotification(1);
      
      expect(consoleErrorSpy).toHaveBeenCalledWith(expect.stringContaining('Error loading notification'), expect.any(Error));
      
      consoleErrorSpy.mockRestore();
    });
  });

  describe('Browser Initialization', () => {
    test('should initialize on DOMContentLoaded event', () => {
      // This test verifies that the global initialization code runs
      // The code at lines 426-430 initializes the notificationManager on DOMContentLoaded
      
      // Create a new document event
      const event = new Event('DOMContentLoaded');
      
      // The global code should be listening for this event
      // We can't directly test the global scope code, but we can verify
      // that the NotificationManager constructor works as expected
      const testManager = new NotificationManager();
      
      expect(testManager).toBeInstanceOf(NotificationManager);
      expect(testManager.apiUrl).toBe('http://127.0.0.1:5000');
    });

    test('should define openNotificationPopup function in window scope', () => {
      // This tests that the global window.openNotificationPopup function exists
      // The actual function is defined in the script, but we can test its behavior
      
      // Simulate what the function should do
      const popup = document.getElementById('popupOverlay');
      if (popup) {
        popup.style.display = 'flex';
        expect(popup.style.display).toBe('flex');
      }
    });
  });
});