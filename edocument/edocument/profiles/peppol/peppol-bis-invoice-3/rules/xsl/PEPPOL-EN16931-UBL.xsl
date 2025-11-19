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
        <svrl:schematron-output schemaVersion="" title="PEPPOL EN16931 UBL Validation">
            <svrl:ns-prefix-in-attribute-values xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
                                               xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
                                               xmlns:in="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
                                               xmlns:cn="urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2"/>
            <svrl:active-pattern name="PEPPOL-EN16931-UBL"/>

            <!-- PEPPOL-specific validation rules -->
            <xsl:call-template name="validate-business-process"/>
            <xsl:call-template name="validate-empty-elements"/>
            <xsl:call-template name="validate-electronic-addresses"/>
            <xsl:call-template name="validate-tax-total"/>
            <xsl:call-template name="validate-peppol-specific-rules"/>
        </svrl:schematron-output>
    </xsl:template>

    <xsl:template name="validate-business-process">
        <!-- PEPPOL-EN16931-R001: Business process MUST be provided -->
        <xsl:if test="not(cbc:ProfileID)">
            <svrl:failed-assert test="cbc:ProfileID" id="PEPPOL-EN16931-R001" flag="fatal">
                <svrl:text>Business process MUST be provided.</svrl:text>
            </svrl:failed-assert>
        </xsl:if>

        <!-- PEPPOL-EN16931-R007: Business process format validation -->
        <xsl:variable name="profile" select="normalize-space(cbc:ProfileID)"/>
        <xsl:if test="$profile != 'Unknown' and not(matches($profile, '^urn:fdc:peppol.eu:2017:poacc:billing:\d+:\d+\.\d+$'))">
            <svrl:failed-assert test="$profile != 'Unknown'" id="PEPPOL-EN16931-R007" flag="fatal">
                <svrl:text>Business process MUST be in the format 'urn:fdc:peppol.eu:2017:poacc:billing:NN:1.0' where NN indicates the process number.</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-empty-elements">
        <!-- PEPPOL-EN16931-R008: Document MUST not contain empty elements -->
        <xsl:for-each select="//*[not(node()) and string-length(normalize-space(.)) = 0]">
            <svrl:failed-assert test="false()" id="PEPPOL-EN16931-R008" flag="fatal">
                <svrl:text>Document MUST not contain empty elements. Element <xsl:value-of select="name()"/> is empty.</svrl:text>
            </svrl:failed-assert>
        </xsl:for-each>
    </xsl:template>

    <xsl:template name="validate-electronic-addresses">
        <!-- PEPPOL-EN16931-R010: Buyer electronic address MUST be provided -->
        <xsl:if test="not(cac:AccountingCustomerParty/cac:Party/cbc:EndpointID)">
            <svrl:failed-assert test="cbc:EndpointID" id="PEPPOL-EN16931-R010" flag="fatal">
                <svrl:text>Buyer electronic address MUST be provided</svrl:text>
            </svrl:failed-assert>
        </xsl:if>

        <!-- PEPPOL-EN16931-R020: Seller electronic address MUST be provided -->
        <xsl:if test="not(cac:AccountingSupplierParty/cac:Party/cbc:EndpointID)">
            <svrl:failed-assert test="cbc:EndpointID" id="PEPPOL-EN16931-R020" flag="fatal">
                <svrl:text>Seller electronic address MUST be provided</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-tax-total">
        <!-- PEPPOL-EN16931-R053: Only one tax total with tax subtotals MUST be provided -->
        <xsl:if test="count(cac:TaxTotal[cac:TaxSubtotal]) != 1">
            <svrl:failed-assert test="count(cac:TaxTotal[cac:TaxSubtotal]) = 1" id="PEPPOL-EN16931-R053" flag="fatal">
                <svrl:text>Only one tax total with tax subtotals MUST be provided.</svrl:text>
            </svrl:failed-assert>
        </xsl:if>
    </xsl:template>

    <xsl:template name="validate-peppol-specific-rules">
        <!-- PEPPOL-EN16931-R003: Buyer reference or order reference must be provided -->
        <xsl:if test="not(cbc:BuyerReference) and not(cac:OrderReference/cbc:ID)">
            <svrl:failed-assert test="cbc:BuyerReference or cac:OrderReference/cbc:ID" id="PEPPOL-EN16931-R003" flag="fatal">
                <svrl:text>Buyer reference or purchase order reference must be provided</svrl:text>
            </svrl:failed-assert>
        </xsl:if>

        <!-- PEPPOL-EN16931-R041: Allowance/charge base amount when percentage provided -->
        <xsl:for-each select="cac:AllowanceCharge">
            <xsl:if test="cbc:MultiplierFactorNumeric and not(cbc:BaseAmount)">
                <svrl:failed-assert test="false()" id="PEPPOL-EN16931-R041" flag="fatal">
                    <svrl:text>Allowance/charge base amount MUST be provided when allowance/charge percentage is provided.</svrl:text>
                </svrl:failed-assert>
            </xsl:if>
        </xsl:for-each>

        <!-- PEPPOL-EN16931-R042: Allowance/charge percentage when base amount provided -->
        <xsl:for-each select="cac:AllowanceCharge">
            <xsl:if test="cbc:BaseAmount and not(cbc:MultiplierFactorNumeric)">
                <svrl:failed-assert test="false()" id="PEPPOL-EN16931-R042" flag="fatal">
                    <svrl:text>Allowance/charge percentage MUST be provided when allowance/charge base amount is provided.</svrl:text>
                </svrl:failed-assert>
            </xsl:if>
        </xsl:for-each>
    </xsl:template>

</xsl:stylesheet>
