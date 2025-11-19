<?xml version="1.0" encoding="UTF-8"?>
<xsl:stylesheet xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:xs="http://www.w3.org/2001/XMLSchema"
                xmlns:svrl="http://purl.oclc.org/dsdl/svrl"
                xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                xmlns:in="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                xmlns:cn="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"
                version="2.0"
                exclude-result-prefixes="xs">

    <xsl:output method="xml" indent="yes" encoding="UTF-8"/>

    <xsl:template match="/">
        <svrl:schematron-output schemaVersion="" title="CEN EN16931 UBL Validation">
            <svrl:ns-prefix-in-attribute-values xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                                               xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                                               xmlns:in="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                                               xmlns:cn="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"/>
            <svrl:active-pattern name="CEN-EN16931-UBL"/>

            <!-- Core EN16931 business rules -->
            <xsl:call-template name="validate-invoice-id"/>
            <xsl:call-template name="validate-buyer-address"/>
            <xsl:call-template name="validate-seller-address"/>
            <xsl:call-template name="validate-invoice-total"/>
            <xsl:call-template name="validate-payment-terms"/>
            <xsl:call-template name="validate-allowance-charge"/>
            <xsl:call-template name="validate-tax-information"/>
        </svrl:schematron-output>
    </xsl:template>

    <xsl:template name="validate-invoice-id">
        <!-- BR-02: Invoice number must be provided -->
        <xsl:if test="not(cbc:ID)">
            <svrl:failed-assert test="cbc:ID" id="BR-02" flag="fatal">
                <svrl:text>An Invoice shall have an Invoice number (BT-1).</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-buyer-address">
        <!-- BR-11: Buyer country code must be provided -->
        <xsl:if test="not(cac:AccountingCustomerParty/cac:Party/cac:PostalAddress/cac:Country/cbc:IdentificationCode)">
            <svrl:failed-assert test="cac:Country/cbc:IdentificationCode" id="BR-11" flag="fatal">
                <svrl:text>The Buyer postal address shall contain a Buyer country code (BT-55).</svrl:text>
            </svrl:failed-assert>
        </xsl:if>

        <!-- BR-63: Buyer electronic address scheme must be provided -->
        <xsl:if test="not(cac:AccountingCustomerParty/cac:Party/cbc:EndpointID/@schemeID)">
            <svrl:failed-assert test="@schemeID" id="BR-63" flag="fatal">
                <svrl:text>The Buyer electronic address (BT-49) shall have a Scheme identifier.</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-seller-address">
        <!-- BR-10: Seller country code must be provided -->
        <xsl:if test="not(cac:AccountingSupplierParty/cac:Party/cac:PostalAddress/cac:Country/cbc:IdentificationCode)">
            <svrl:failed-assert test="cac:Country/cbc:IdentificationCode" id="BR-10" flag="fatal">
                <svrl:text>The Seller postal address shall contain a Seller country code (BT-40).</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-invoice-total">
        <!-- BR-16: Invoice total amount must be provided -->
        <xsl:if test="not(cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount)">
            <svrl:failed-assert test="cbc:TaxInclusiveAmount" id="BR-16" flag="fatal">
                <svrl:text>An Invoice shall have the Invoice total amount with VAT (BT-112).</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-payment-terms">
        <!-- BR-CO-25: Payment due date or terms must be provided for positive amounts -->
        <xsl:variable name="total" select="number(cac:LegalMonetaryTotal/cbc:PayableAmount)"/>
        <xsl:if test="$total &gt; 0 and not(cbc:DueDate) and not(cac:PaymentTerms/cbc:Note)">
            <svrl:failed-assert test="((. > 0) and (exists(//cbc:DueDate) or exists(//cac:PaymentTerms/cbc:Note))) or (. &lt;= 0)" id="BR-CO-25" flag="fatal">
                <svrl:text>In case the Amount due for payment (BT-115) is positive, either the Payment due date (BT-9) or the Payment terms (BT-20) shall be present.</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-allowance-charge">
        <!-- BR-31: Document level allowance amount must be provided -->
        <xsl:for-each select="cac:AllowanceCharge">
            <xsl:if test="not(cbc:Amount)">
                <svrl:failed-assert test="exists(cbc:Amount)" id="BR-31" flag="fatal">
                    <svrl:text>Each Document level allowance (BG-20) shall have a Document level allowance amount (BT-92).</svrl:text>
                </svrl:failed-assert>
            </xsl:if>
        </xsl:for-each>

        <!-- BR-33: Allowance reason must be provided -->
        <xsl:for-each select="cac:AllowanceCharge">
            <xsl:if test="not(cbc:AllowanceChargeReason) and not(cbc:AllowanceChargeReasonCode)">
                <svrl:failed-assert test="exists(cbc:AllowanceChargeReason) or exists(cbc:AllowanceChargeReasonCode)" id="BR-33" flag="fatal">
                    <svrl:text>Each Document level allowance (BG-20) shall have a Document level allowance reason (BT-97) or a Document level allowance reason code (BT-98).</svrl:text>
                </svrl:failed-assert>
            </xsl:if>
        </xsl:for-each>
    </xsl:template>

    <xsl:template name="validate-tax-information">
        <!-- BR-45: Invoice tax amount must be provided when VAT is applicable -->
        <xsl:if test="cac:TaxTotal and not(cac:TaxTotal/cbc:TaxAmount)">
            <svrl:failed-assert test="cbc:TaxAmount" id="BR-45" flag="fatal">
                <svrl:text>Each Invoice tax amount (BT-110) shall be provided.</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

</xsl:stylesheet>
