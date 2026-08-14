# Payroll, HR & Accounting Modules Documentation

## Overview

This document provides comprehensive guidance on using the Payroll, HR (Human Resources), and Accounting modules integrated into the 14XL ERP System.

## Installation & Setup

### 1. Apply Migrations

After pulling the latest code, run the following commands to apply database migrations:

```bash
# (already at repo root)
python manage.py makemigrations
python manage.py migrate
```

This will create all necessary database tables for the three new modules.

### 2. Create Superuser (if needed)

```bash
python manage.py createsuperuser
```

### 3. Access Admin Dashboard

Navigate to: `http://localhost:8000/admin/`

---

## Payroll Module

### Features

- **Salary Structures**: Define different compensation packages
- **Allowances**: Add various types of allowances (fixed, percentage-based, variable)
- **Deductions**: Configure deductions (tax, insurance, etc.)
- **Employee Salary Setup**: Customize salary configuration for each employee
- **Overtime Rules**: Define overtime calculation multipliers for different day types
- **Payroll Periods**: Create monthly/bi-weekly/weekly payroll cycles
- **Payroll Runs**: Process payroll for multiple employees
- **Payslips**: Generate individual employee payment statements
- **Payment Integration**: Support for bank transfers and M-Pesa
- **Payment Tracking**: Record and reconcile actual payments

### Quick Start

1. **Create Salary Structures**:
   - Navigate to: `/payroll/structures/`
   - Click "Create" and define basic salary for role types
   - Examples: "Standard", "Senior", "Manager"

2. **Define Allowances & Deductions**:
   - Go to: `/payroll/allowances/` and `/payroll/deductions/`
   - Create components like "House Allowance", "Medical Insurance", etc.
   - Set type: Fixed, Percentage of Basic, or Variable

3. **Setup Employee Salaries**:
   - Create employee record in HR module first
   - Then go to Salary Setup and assign structure + allowances/deductions
   - Set effective date

4. **Create Payroll Period**:
   - Navigate to: `/payroll/periods/create/`
   - Define start date, end date, and payment date
   - Set period type (monthly, bi-weekly, etc.)

5. **Process Payroll**:
   - Go to: `/payroll/runs/`
   - Create new payroll run
   - Generate payslips for all active employees
   - Review calculations and approve
   - Process payments

### Key Models

| Model | Purpose |
|-------|---------|
| `SalaryStructure` | Base salary definition |
| `Allowance` | Salary add-ons |
| `Deduction` | Salary deductions |
| `EmployeeSalarySetup` | Per-employee salary config |
| `OvertimeRule` | Overtime multipliers |
| `PayrollPeriod` | Payment cycle |
| `PayrollRun` | Single payroll processing |
| `Payslip` | Individual pay statement |
| `PaymentIntegration` | Payment gateway config |
| `PaymentRecord` | Actual payment transaction |

### Workflow

```
Define Structures → Add Allowances/Deductions → Setup Employee Salaries 
→ Create Payroll Period → Process Payroll → Generate Payslips → Process Payments
```

---

## HR Module

### Features

- **Employee Management**: Centralized employee database with personal/employment details
- **Department Management**: Organize employees by departments
- **Position Hierarchy**: Define job titles and reporting structures
- **Leave Management**: Request, approve, and track employee leaves
- **Attendance Tracking**: Record daily employee attendance
- **Employee Advances**: Manage salary advances and repayment schedules
- **Performance Reviews**: Conduct and record performance evaluations
- **Training Programs**: Track training participation and development
- **Recruitment**: Manage job openings and applications
- **Organization Structure**: Define company hierarchy
- **Employee Portal**: Self-service for leave requests and document access

### Quick Start

1. **Create Departments**:
   - Navigate to: `/hr/departments/`
   - Add departments (IT, HR, Sales, Operations, etc.)
   - Assign department managers

2. **Define Positions**:
   - Go to: `/hr/departments/` → View department → Add Position
   - Create roles like "Software Developer", "Manager", etc.
   - Set reporting hierarchy

3. **Add Employees**:
   - Navigate to: `/hr/employees/create/`
   - Link to Django User account
   - Fill in personal information (DOB, contact details, etc.)
   - Assign department and position
   - Set employment type and status

4. **Define Leave Types**:
   - Go to: HR Admin → Leave Type
   - Create: Annual Leave, Sick Leave, Casual Leave, etc.
   - Set days available per year

5. **Process Leave Requests**:
   - Employee: `/hr/leave-requests/create/` → Submit request
   - Manager: `/hr/leave-requests/` → Review and Approve/Reject

6. **Track Attendance**:
   - Navigate to: `/hr/attendance/`
   - Create daily attendance records
   - Mark: Present, Absent, Late, Half Day, On Leave

7. **Manage Employee Advances**:
   - Employee: `/hr/advances/create/` → Request advance
   - Manager: `/hr/advances/` → Review and approve
   - System calculates monthly deduction

8. **Performance Reviews**:
   - Manager: `/hr/performance-reviews/` → Create review
   - Rate employee (1-5 scale)
   - Document strengths, improvement areas, goals

9. **Recruitment**:
   - HR: `/hr/recruitment/create/` → Post job opening
   - Track applications at: `/hr/applications/`
   - Update application status (submitted → interview → offer → hired)

### Key Models

| Model | Purpose |
|-------|---------|
| `Employee` | Employee master data |
| `Department` | Organizational units |
| `Position` | Job titles and hierarchy |
| `LeaveType` | Types of leave available |
| `LeaveRequest` | Leave application |
| `Attendance` | Daily attendance |
| `EmployeeAdvance` | Salary advance tracking |
| `PerformanceReview` | Performance evaluation |
| `Training` | Training programs |
| `EmployeeTraining` | Training participation |
| `Recruitment` | Job openings |
| `JobApplication` | Candidate applications |

### Employee Status Values

- **Active**: Currently employed
- **Inactive**: Not working but record retained
- **On Leave**: Currently on leave
- **Terminated**: Employment ended
- **Resigned**: Employee resigned

---

## Accounting Module

### Features

- **Chart of Accounts**: Full GL account structure (Assets, Liabilities, Equity, Revenue, Expenses)
- **Journal Entry**: Post transactions to GL
- **Invoices**: Create and track sales invoices
- **Bills**: Manage purchase bills and payables
- **Bank Accounts**: Track bank and cash accounts
- **Bank Reconciliation**: Reconcile bank statements with GL
- **Budget Planning**: Create and monitor budgets vs actual
- **Financial Reporting**: Income Statement, Balance Sheet, Trial Balance, Cash Flow
- **Tax Configuration**: Setup VAT and tax rules
- **M-Pesa Integration**: Record M-Pesa transactions
- **Accounts Receivable**: Track customer invoices and payments
- **Accounts Payable**: Track vendor bills and payments

### Quick Start

1. **Setup Chart of Accounts**:
   - Navigate to: `/accounting/chart-of-accounts/`
   - Create accounts for each type:
     - Assets: Cash (1000), Bank (1001), Receivables (1200)
     - Liabilities: Payables (2100), Taxes (2200)
     - Equity: Capital (3100), Retained Earnings (3200)
     - Revenue: Sales (4100), Services (4200)
     - Expenses: Salary (5100), Rent (5200), Utilities (5300)
   - Set opening balances

2. **Create Journals**:
   - Go to: `/accounting/journals/create/`
   - Create: General Journal, Sales Journal, Purchase Journal, Cash Journal

3. **Process Journal Entries**:
   - Navigate to: `/accounting/entries/create/`
   - Create double-entry transactions
   - Link to related documents (invoice, bill)
   - Post to General Ledger

4. **Create Invoices**:
   - Go to: `/accounting/invoices/create/`
   - Add invoice lines with quantity, price, tax
   - System auto-calculates totals
   - Send to customer

5. **Record Received Payments**:
   - View invoice: `/accounting/invoices/<id>/`
   - Click "Mark as Paid" when payment received
   - Record payment method and reference

6. **Record Bills**:
   - Navigate to: `/accounting/bills/create/`
   - Add vendor bill details and line items
   - Schedule payment

7. **Bank Management**:
   - Create bank accounts: `/accounting/bank-accounts/create/`
   - Record transactions: `/accounting/transactions/create/`
   - Types: Deposits, Withdrawals, Transfers, Checks

8. **Bank Reconciliation**:
   - Navigate to: `/accounting/reports/bank-reconciliation/`
   - Compare bank statement with GL
   - Mark transactions as reconciled
   - Report differences

9. **Budgeting**:
   - Create budget: `/accounting/budgets/create/`
   - Set budget amounts per account per period
   - System tracks actual vs budgeted spending

10. **Financial Reports**:
    - Trial Balance: `/accounting/reports/trial-balance/`
    - Income Statement: `$PENDING_IMPLEMENTATION$`
    - Balance Sheet: `$PENDING_IMPLEMENTATION$`
    - Cash Flow: `$PENDING_IMPLEMENTATION$`

### Key Models

| Model | Purpose |
|-------|---------|
| `ChartOfAccounts` | GL account structure |
| `Journal` | Transaction journals |
| `JournalEntry` | GL transactions |
| `Invoice` | Sales documents |
| `InvoiceItem` | Invoice line items |
| `Bill` | Purchase documents |
| `BillItem` | Bill line items |
| `BankAccount` | Bank/cash accounts |
| `BankTransaction` | Bank movements |
| `BankReconciliation` | Statement reconciliation |
| `Budget` | Budget master |
| `BudgetLine` | Budget details |
| `FinancialReport` | Generated reports |
| `TaxConfiguration` | Tax setup |
| `MPesaIntegration` | M-Pesa config |
| `MPesaTransaction` | M-Pesa payments |

### Account Types

- **Asset**: Increase with Debit, Decrease with Credit
- **Liability**: Increase with Credit, Decrease with Debit
- **Equity**: Increase with Credit, Decrease with Debit
- **Revenue**: Increase with Credit, Decrease with Debit
- **Expense**: Increase with Debit, Decrease with Credit

### Invoice Statuses

- **Draft**: Not yet issued
- **Issued**: Sent to customer
- **Sent**: Acknowledged by customer
- **Partial**: Partially paid
- **Paid**: Full payment received
- **Overdue**: Payment past due date
- **Cancelled**: Invoice cancelled

---

## Integration Between Modules

### Payroll → Accounting

When payroll runs and payments are processed:
1. Journal entries are created automatically
2. DR: Salary Expense (5100)
3. CR: Bank Account (1001) or Payables (2100)

### HR → Payroll

Employee salary setup from HR feeds into Payroll:
- Employee records linked
- Salary structures assigned
- Leave deductions calculated

### Accounting → Reports

Financial data flows to reporting:
- Revenue from invoices
- Expenses from bills and payroll
- Cash flow from bank transactions

---

## User Permissions

### Payroll Manager
- Create/approve payroll runs
- Generate payslips
- Process payments
- View reports

### HR Manager
- Create/edit employees
- Approve leave requests
- Create job postings
- View attendance

### Accountant
- Create/post journal entries
- Create invoices and bills
- Bank reconciliation
- Budget management

### Finance Manager
- View all financial reports
- Approve high-value transactions
- Budget monitoring
- Financial analysis

---

## Troubleshooting

### Issue: "Payroll run created but no payslips generated"
**Solution**: Ensure employees have salary setup configured with valid structure.

### Issue: "Bank reconciliation showing mismatch"
**Solution**: Check for bank fees, timing differences, or unrecorded transactions.

### Issue: "Invoice total doesn't match items"
**Solution**: Verify tax rate calculations and ensure all items are added.

### Issue: "Employee advance monthly deduction not appearing in payslip"
**Solution**: Add advance deduction to payroll period before generating payslips.

---

## API Endpoints (REST Framework)

Coming in next phase:
- `/api/payroll/payslips/`
- `/api/hr/employees/`
- `/api/accounting/invoices/`

---

## Support & Documentation

- Django Admin: http://localhost:8000/admin/
- Dashboard: http://localhost:8000/
- API Documentation: [Pending]

---

**Last Updated**: June 2026
**Version**: 1.0
**Compatibility**: Django 6.0+, Python 3.10+
